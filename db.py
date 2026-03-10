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
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)

def save_detection(video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO detections (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence) VALUES (?,?,?,?,?,?)",
            (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence)
        )

def get_detections(video_file=None):
    with get_conn() as conn:
        if video_file:
            return conn.execute(
                "SELECT * FROM detections WHERE video_file=? ORDER BY timestamp_sec", (video_file,)
            ).fetchall()
        return conn.execute("SELECT * FROM detections ORDER BY created_at DESC, timestamp_sec").fetchall()
