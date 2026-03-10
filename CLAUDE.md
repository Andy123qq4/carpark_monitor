# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the plate processor on a video file
python processor.py video/"GF15 20260212 142142-145519.avi"

# Start the dashboard web server
uvicorn app:app --reload
```

## Architecture

**Two-process system** — processor and web server are decoupled, communicating only via SQLite.

- **`processor.py`** — CLI batch job. Opens a video, extracts every 5th frame via OpenCV, runs fast-alpr (YOLO v9 + ONNX) to detect plates, validates against HK plate regex (`[A-Z]{1,2}\s?[0-9]{1,4}`), saves annotated JPEGs to `data/detections/`, writes rows to SQLite.
- **`db.py`** — Data access layer. `init_db()` creates the table + unique index + runs migrations. `save_detection()` uses `INSERT OR IGNORE` for idempotency. `get_plate_sessions()` uses SQL window functions (LAG → SUM → ROW_NUMBER) to group raw detections into per-plate visits with a 30s gap threshold.
- **`app.py`** — FastAPI server. Single `GET /` endpoint renders `templates/index.html` via Jinja2. Serves annotated frames as static files under `/detections/`.

**Camera ID** is parsed from the video filename stem (first word before space, e.g. `GF15`).

**File naming**: `data/detections/{camera_id}_{frame_num}_{plate_text}.jpg` (annotated full frame) and `{..}_crop.jpg` (plate patch). Dashboard tries crop first, falls back to full frame on 404.

## Constraints

- Keep `processor.py` as a single runnable script — no async, no task queues
- `app.py` is read-only from DB — never writes
- No defensive try/except unless explicitly requested
- SQLite only — no ORM, no migrations framework
