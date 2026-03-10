# INPUT: none (creates DB file on import)
# OUTPUT: init_db(), save_detection(), get_detections()
# ROLE: data access layer — SQLite read/write for plate detections

import sqlite3
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
