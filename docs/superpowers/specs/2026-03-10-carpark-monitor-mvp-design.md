# Carpark Monitor MVP Design

## Goal

Process individual CCTV .avi files to detect and read Hong Kong car plates, store results in SQLite, and display them via a simple web dashboard. MVP validates ALPR accuracy before building the full entry/exit pipeline.

## Decisions

- **Camera setup**: 4 cameras — GF15/GF17 (entry), GF16/GF18 (exit)
- **Processing mode**: Batch (pre-recorded .avi files)
- **Plates**: Hong Kong format (`AB 1234` or `A1234` etc.)
- **ALPR**: `fast-alpr` — pure Python, ONNX-based, no C++ build pain
- **Output**: Web dashboard (FastAPI + plain HTML/JS)
- **DB**: SQLite
- **Deduplication**: Same plate within 60s time window = one event (post-MVP)

## MVP Architecture

```
video/*.avi
    ↓ cv2 (every Nth frame)
processor.py
    ↓ fast-alpr
plate text + confidence
    ↓ HK regex validation
db.py (SQLite)
    ↓
app.py (FastAPI)
    ↓
templates/index.html
```

## File Structure

```
carpark_monitor/
├── video/                  ← .avi input files
├── data/                   ← carpark.db (SQLite)
├── templates/
│   └── index.html          ← dashboard HTML
├── db.py                   ← DB init + read/write helpers
├── processor.py            ← video → frames → ALPR → DB
├── app.py                  ← FastAPI server
└── requirements.txt
```

## DB Schema

```sql
CREATE TABLE detections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_file  TEXT NOT NULL,
    camera_id   TEXT NOT NULL,
    frame_num   INTEGER NOT NULL,
    timestamp_sec REAL NOT NULL,
    plate_text  TEXT NOT NULL,
    confidence  REAL NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
```

## HK Plate Regex

```
^[A-Z]{1,2}\s?[0-9]{1,4}$
```
e.g. `AB 1234`, `A 123`, `AB1234`
