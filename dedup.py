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
        'V': 'ANBHMY',   # V looks like A, N, B, H, M, Y
        'Y': 'V',        # Y looks like V
        'D': 'O0B',      # D looks like O, 0, B
        'O': 'D0Q',      # O looks like D, 0, Q
        '0': 'ODQ86',    # 0 looks like O, D, Q, 8, 6
        '8': '93658B0',  # 8 looks like 9, 3, 6, 5, B, 0
        '9': '8',        # 9 looks like 8
        '6': '8G50',     # 6 looks like 8, G, 5, 0
        '5': 'S86',      # 5 looks like S, 8, 6
        'S': '5',        # S looks like 5
        '3': '8B',       # 3 looks like 8, B
        'B': '8D',       # B looks like 8, D
        '1': 'I7',       # 1 looks like I, 7
        'I': '1',        # I looks like 1
        '7': '1Z',       # 7 looks like 1, Z
        '2': 'Z',        # 2 looks like Z
        'Z': '27',       # Z looks like 2, 7
        '4': 'A',        # 4 looks like A
        'A': 'V4',       # A looks like V, 4
        'N': 'VW',       # N looks like V, W
        'H': 'V',        # H looks like V
        'M': 'VWN',      # M looks like V, W, N
        'W': 'MNV',      # W looks like M, N, V
    }
    if a == b:
        return True
    return b in confusions.get(a, '') or a in confusions.get(b, '')


def plates_similar(p1: str, p2: str) -> bool:
    """Check if two plates are likely the same with OCR errors.

    For same-length plates: levenshtein ≤ 2 AND all differing chars must be confusable.
    For different-length plates: levenshtein ≤ 2 (handles dropped/inserted chars).
    """
    p1 = p1.replace(' ', '')
    p2 = p2.replace(' ', '')

    if p1 == p2:
        return True
    if levenshtein(p1, p2) > 2:
        return False
    if len(p1) != len(p2):
        return True  # within edit distance — accept length variation

    # Same length: require all diffs to be confusable character pairs
    diffs = [(a, b) for a, b in zip(p1, p2) if a != b]
    return all(char_similarity(a, b) for a, b in diffs)


def normalize_plate(text: str) -> str:
    """Apply position-aware correction for HK plate format [A-Z]{1,2}[0-9]{1,4}.

    At letter positions (0–1): correct digit lookalikes → letters (e.g. 8→B, 0→O).
    At digit positions (2+): correct letter lookalikes → digits (e.g. B→8, O→0).
    """
    text = text.replace(' ', '').upper()
    if not text:
        return text

    DIGIT_TO_LETTER = {'0': 'O', '1': 'I', '2': 'Z', '4': 'A', '5': 'S', '6': 'G', '8': 'B'}
    LETTER_TO_DIGIT = {'O': '0', 'I': '1', 'Z': '2', 'A': '4', 'S': '5', 'G': '6', 'B': '8'}

    # Detect letter/digit boundary: find first pure digit char at index >= 1
    # (skip index 0 — HK plates always start with at least one letter, even if OCR misread it)
    split = len(text)
    for i, c in enumerate(text):
        if c.isdigit() and i >= 1:
            split = i
            break
    # If no pure digit found, check for letter-in-digit-position lookalikes
    if split == len(text):
        for i, c in enumerate(text):
            if c in LETTER_TO_DIGIT and i >= 1:
                split = i
                break
    # Clamp to valid HK prefix range [1, 2]
    split = max(1, min(2, split))

    result = []
    for i, c in enumerate(text):
        if i < split:
            result.append(DIGIT_TO_LETTER.get(c, c))
        else:
            result.append(LETTER_TO_DIGIT.get(c, c))
    return ''.join(result)


def bbox_iou(b1, b2) -> float:
    """Intersection-over-Union for two (x, y, w, h) bboxes."""
    if not b1 or not b2:
        return 0.0
    x1, y1, w1, h1 = b1
    x2, y2, w2, h2 = b2
    ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
    inter = ix * iy
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0.0


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
        found = False
        for group in groups:
            if any(plates_similar(text, g[0]) for g in group):
                group.append((text, conf, bbox))
                found = True
                break
        if not found:
            groups.append([(text, conf, bbox)])

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
                if any(
                    plates_similar(text, r[0]) or bbox_iou(bbox, r[2]) > 0.3
                    for r in cluster['reads']
                ):
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
        """Pick winning plate text by summing confidence scores, then normalize."""
        votes: dict[str, float] = {}
        for text, conf, *_ in reads:
            votes[text] = votes.get(text, 0.0) + conf
        best_text = max(votes, key=votes.get)
        best = max((r for r in reads if r[0] == best_text), key=lambda r: r[1])
        normalized = normalize_plate(best_text)
        return (normalized,) + best[1:]
