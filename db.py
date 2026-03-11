# INPUT: none (creates DB file on import)
# OUTPUT: init_db(), save_detection(), get_detections(), get_plate_sessions(), merge_stationary_sessions(), get_annotation_events()
# ROLE: data access layer — SQLite read/write for plate detections

import math
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("data/carpark.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                video_file    TEXT NOT NULL,
                camera_id     TEXT NOT NULL,
                frame_num     INTEGER NOT NULL,
                timestamp_sec REAL NOT NULL,
                plate_text    TEXT NOT NULL,
                confidence    REAL NOT NULL,
                bbox_x        INTEGER,
                bbox_y        INTEGER,
                bbox_w        INTEGER,
                bbox_h        INTEGER,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        # Migration: add bbox columns if they don't exist
        columns = [row[1] for row in conn.execute("PRAGMA table_info(detections)")]
        if 'bbox_x' not in columns:
            conn.execute("ALTER TABLE detections ADD COLUMN bbox_x INTEGER")
            conn.execute("ALTER TABLE detections ADD COLUMN bbox_y INTEGER")
            conn.execute("ALTER TABLE detections ADD COLUMN bbox_w INTEGER")
            conn.execute("ALTER TABLE detections ADD COLUMN bbox_h INTEGER")
            print("✓ Added bbox columns to existing detections table")
        conn.execute("""
            DELETE FROM detections
            WHERE id NOT IN (
                SELECT MIN(id) FROM detections
                GROUP BY video_file, frame_num, plate_text
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup
            ON detections(video_file, frame_num, plate_text)
        """)

def save_detection(video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence, bbox=None):
    with get_conn() as conn:
        if bbox:
            x, y, w, h = bbox
            conn.execute(
                "INSERT OR IGNORE INTO detections (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence, bbox_x, bbox_y, bbox_w, bbox_h) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence, x, y, w, h)
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO detections (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence) VALUES (?,?,?,?,?,?)",
                (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence)
            )

def get_detections(video_file=None):
    with get_conn() as conn:
        if video_file:
            return conn.execute(
                "SELECT * FROM detections WHERE video_file=? ORDER BY timestamp_sec", (video_file,)
            ).fetchall()
        return conn.execute("SELECT * FROM detections ORDER BY created_at DESC, timestamp_sec").fetchall()

def get_plate_sessions(video_file=None, gap_sec=30):
    """Group raw detections into per-plate visits using a time-gap threshold.
    Returns one best (highest confidence) detection per session, plus frame_count."""
    where = "WHERE video_file = ?" if video_file else ""
    params = [video_file, gap_sec] if video_file else [gap_sec]
    sql = f"""
        WITH ordered AS (
            SELECT *,
                LAG(timestamp_sec) OVER (
                    PARTITION BY video_file, plate_text ORDER BY timestamp_sec
                ) AS prev_ts
            FROM detections
            {where}
        ),
        sessioned AS (
            SELECT *,
                SUM(CASE WHEN prev_ts IS NULL OR timestamp_sec - prev_ts > ? THEN 1 ELSE 0 END)
                    OVER (PARTITION BY video_file, plate_text ORDER BY timestamp_sec) AS session_id
            FROM ordered
        ),
        ranked AS (
            SELECT *,
                COUNT(*) OVER (PARTITION BY video_file, plate_text, session_id) AS frame_count,
                ROW_NUMBER() OVER (
                    PARTITION BY video_file, plate_text, session_id ORDER BY confidence DESC
                ) AS rn
            FROM sessioned
        )
        SELECT * FROM ranked WHERE rn = 1
        ORDER BY timestamp_sec DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [{"detection": r, "frame_count": r["frame_count"]} for r in rows]


def _centroid(det: dict) -> tuple[float, float] | None:
    if det.get("bbox_x") is None:
        return None
    return (det["bbox_x"] + det["bbox_w"] / 2, det["bbox_y"] + det["bbox_h"] / 2)


def _dist(a: tuple, b: tuple) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def merge_stationary_sessions(
    sessions: list[dict],
    max_gap_sec: float = 1800,
    max_dist_px: float = 300,
) -> list[dict]:
    """Merge same-plate sessions at similar bbox positions into one, marking is_stationary=True.

    Input: list of {"detection": dict|sqlite3.Row, "frame_count": int}
    Output: same structure with added "is_stationary": bool, merged rows removed.
    """
    if not sessions:
        return []

    def _to_dict(s):
        det = s["detection"]
        if not isinstance(det, dict):
            det = {k: det[k] for k in det.keys()}
        return {"detection": det, "frame_count": s["frame_count"], "is_stationary": False}

    items = [_to_dict(s) for s in sessions]

    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, s in enumerate(items):
        key = (s["detection"]["video_file"], s["detection"]["plate_text"])
        groups[key].append(i)

    to_remove: set[int] = set()

    for indices in groups.values():
        if len(indices) < 2:
            continue
        indices.sort(key=lambda i: items[i]["detection"]["timestamp_sec"])

        clusters: list[list[int]] = [[indices[0]]]
        for idx in indices[1:]:
            cur = items[idx]["detection"]
            last = items[clusters[-1][-1]]["detection"]
            gap = cur["timestamp_sec"] - last["timestamp_sec"]
            c1, c2 = _centroid(last), _centroid(cur)
            if gap <= max_gap_sec and c1 and c2 and _dist(c1, c2) <= max_dist_px:
                clusters[-1].append(idx)
            else:
                clusters.append([idx])

        for cluster in clusters:
            if len(cluster) < 2:
                continue
            best_idx = max(cluster, key=lambda i: items[i]["detection"]["confidence"])
            earliest_idx = min(cluster, key=lambda i: items[i]["detection"]["timestamp_sec"])
            merged_det = {**items[best_idx]["detection"],
                          "timestamp_sec": items[earliest_idx]["detection"]["timestamp_sec"]}
            primary = cluster[0]
            items[primary]["detection"] = merged_det
            items[primary]["is_stationary"] = True
            items[primary]["frame_count"] = sum(items[i]["frame_count"] for i in cluster)
            for i in cluster[1:]:
                to_remove.add(i)

    result = [s for i, s in enumerate(items) if i not in to_remove]
    return sorted(result, key=lambda s: s["detection"]["timestamp_sec"], reverse=True)


def get_annotation_events(video_file: str, gap_sec: float = 10.0) -> list[dict]:
    rows = get_detections(video_file=video_file)
    if not rows:
        return []

    events: list[list] = []
    for row in sorted(rows, key=lambda r: r["timestamp_sec"]):
        if not events or row["timestamp_sec"] - events[-1][-1]["timestamp_sec"] > gap_sec:
            events.append([])
        events[-1].append(row)

    result = []
    for i, group in enumerate(events):
        result.append({
            "event_id": i,
            "video_file": video_file,
            "start_ts": group[0]["timestamp_sec"],
            "end_ts": group[-1]["timestamp_sec"],
            "detections": [
                {k: d[k] for k in d.keys()}
                for d in sorted(group, key=lambda r: r["confidence"], reverse=True)
            ],
        })
    return result
