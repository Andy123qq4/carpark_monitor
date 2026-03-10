# INPUT: raw plate detections from ALPR
# OUTPUT: deduplicated, refined plate readings
# ROLE: post-processing — group similar readings, apply consensus, filter false positives


def levenshtein(s1: str, s2: str) -> int:
    """Edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def char_similarity(a: str, b: str) -> bool:
    """Check if two characters are commonly confused in OCR."""
    confusions = {
        'V': 'ANBHM',  # V looks like A, N, B, H, M
        'D': 'O0',     # D looks like O, 0
        'O': 'D0Q',    # O looks like D, 0, Q
        '0': 'ODQ',    # 0 looks like O, D, Q
        '8': '93658B', # 8 looks like 9, 3, 6, 5, B
        '9': '8',      # 9 looks like 8
        '6': '8G5',    # 6 looks like 8, G, 5
        '5': 'S86',    # 5 looks like S, 8, 6
        'S': '5',      # S looks like 5
        '3': '8B',     # 3 looks like 8, B
        'B': '8',      # B looks like 8
        '1': 'I7',     # 1 looks like I, 7
        'I': '1',      # I looks like 1
        '7': '1',      # 7 looks like 1
        '2': 'Z',      # 2 looks like Z
        'Z': '2',      # Z looks like 2
        '4': 'A',      # 4 looks like A
        'A': 'V4',     # A looks like V, 4
        'N': 'V',      # N looks like V
        'H': 'V',      # H looks like V
        'M': 'V',      # M looks like V
    }
    if a == b:
        return True
    return b in confusions.get(a, '') or a in confusions.get(b, '')


def plates_similar(p1: str, p2: str) -> bool:
    """Check if two plates are likely the same with OCR errors."""
    # Remove spaces for comparison
    p1_clean = p1.replace(' ', '')
    p2_clean = p2.replace(' ', '')
    
    # Must be same length
    if len(p1_clean) != len(p2_clean):
        return False
    
    # Count character differences
    diffs = [(a, b) for a, b in zip(p1_clean, p2_clean) if a != b]
    
    # Same plate
    if len(diffs) == 0:
        return True
    
    # Allow up to 3 character differences (HK plates are 4-6 chars)
    # but ALL differences must be confusable characters
    if len(diffs) > 3:
        return False
    
    # Check if all differences are confusable characters
    return all(char_similarity(a, b) for a, b in diffs)


def deduplicate_detections(detections: list[tuple[str, float, tuple]]) -> list[tuple[str, float, tuple]]:
    """Group similar plate readings and return the highest-confidence one per group.
    Input: [(plate_text, confidence, bbox), ...]
    Output: deduplicated list with best reading per physical plate"""
    
    if not detections:
        return []
    
    # Sort by confidence descending
    detections = sorted(detections, key=lambda x: x[1], reverse=True)
    
    # Group similar plates
    groups: list[list[tuple]] = []
    for text, conf, bbox in detections:
        # Find existing group this belongs to
        found = False
        for group in groups:
            if any(plates_similar(text, g[0]) for g in group):
                group.append((text, conf, bbox))
                found = True
                break
        if not found:
            groups.append([(text, conf, bbox)])
    
    # Return the highest-confidence detection from each group
    result = []
    for group in groups:
        best = max(group, key=lambda x: x[1])
        result.append(best)
    
    return result


def apply_confidence_threshold(detections: list[tuple[str, float, tuple]], min_conf: float = 0.7) -> list[tuple[str, float, tuple]]:
    """Filter out low-confidence detections."""
    return [(text, conf, bbox) for text, conf, bbox in detections if conf >= min_conf]



class TemporalTracker:
    """Buffer plate reads across frames; emit confidence-voted best on cluster expiry."""

    def __init__(self, hold_frames: int = 30):
        self.hold_frames = hold_frames
        self._next_id = 0
        # cluster_id -> {last_frame, reads: [(text, conf, bbox, crop, frame_num, timestamp_sec)]}
        self.clusters: dict[str, dict] = {}

    def update(self, detections: list[tuple], frame_num: int, timestamp_sec: float) -> list[tuple]:
        """Buffer detections; emit voted results for expired clusters.

        Args:
            detections: [(text, conf, bbox, crop), ...] — crop is a numpy array or None
            frame_num: Current frame number
            timestamp_sec: Current timestamp in seconds

        Returns:
            [(text, conf, bbox, crop, frame_num, timestamp_sec), ...] for expired clusters
        """
        # Emit expired clusters first
        expired = [cid for cid, c in self.clusters.items()
                   if frame_num - c['last_frame'] > self.hold_frames]
        result = []
        for cid in expired:
            result.append(self._vote(self.clusters.pop(cid)['reads']))

        # Assign each detection to an existing cluster or start a new one
        for text, conf, bbox, crop in detections:
            read = (text, conf, bbox, crop, frame_num, timestamp_sec)
            matched_cid = None
            for cid, cluster in self.clusters.items():
                if any(plates_similar(text, r[0]) for r in cluster['reads']):
                    matched_cid = cid
                    break
            if matched_cid:
                self.clusters[matched_cid]['reads'].append(read)
                self.clusters[matched_cid]['last_frame'] = frame_num
            else:
                cid = str(self._next_id)
                self._next_id += 1
                self.clusters[cid] = {'last_frame': frame_num, 'reads': [read]}

        return result

    def flush(self) -> list[tuple]:
        """Emit all remaining clusters (call at end of video)."""
        result = [self._vote(c['reads']) for c in self.clusters.values()]
        self.clusters.clear()
        return result

    def _vote(self, reads: list[tuple]) -> tuple:
        """Pick winning plate text by summing confidence scores; return best individual read."""
        votes: dict[str, float] = {}
        for text, conf, *_ in reads:
            votes[text] = votes.get(text, 0.0) + conf
        best_text = max(votes, key=votes.get)
        return max((r for r in reads if r[0] == best_text), key=lambda r: r[1])

