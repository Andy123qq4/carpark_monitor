# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the plate processor on a video file (use MP4, not AVI — see AVI fps bug below)
python processor.py "video/GF15 20260212 142142-145519.mp4"

# Start the dashboard web server
uvicorn app:app --reload
```

## Architecture

**Two-process system** — processor and web server are decoupled, communicating only via SQLite.

- **`processor.py`** — CLI batch job. Opens a video, extracts every 5th frame via OpenCV, runs fast-alpr (YOLO v9 + ONNX) to detect plates, validates against HK plate regex (`[A-Z]{1,2}\s?[0-9]{1,4}`), saves crop JPEGs to `data/detections/`, writes rows to SQLite.
- **`dedup.py`** — Post-processing. `TemporalTracker` buffers reads per plate cluster and emits the confidence-voted best text on cluster expiry (P1). `plates_similar()` groups OCR variants using edit distance + confusion map.
- **`db.py`** — Data access layer. `init_db()` creates the table + unique index + runs migrations. `save_detection()` uses `INSERT OR IGNORE` for idempotency. `get_plate_sessions()` uses SQL window functions (LAG → SUM → ROW_NUMBER) to group raw detections into per-plate visits with a 30s gap threshold.
- **`app.py`** — FastAPI server. Single `GET /` endpoint renders `templates/index.html` via Jinja2. Serves crop frames as static files under `/detections/`. Also serves MJPEG clip stream and SSE realtime processing.

**Camera ID** is parsed from the video filename stem (first word before space, e.g. `GF15`).

**File naming**: `data/detections/{camera_id}_{frame_num}_{plate_text}_crop.jpg` (plate crop only — full annotated frames removed).

## ⚠️ AVI FPS Bug

The AVI files from this camera system report wrong fps in the container header. **Always use the MP4 versions** (converted via `ffmpeg -c:v libx264`):

| Camera | AVI fps (wrong) | Actual fps | Video file to use |
|---|---|---|---|
| GF15 | 30 | 12.5 | `GF15 20260212 142142-145519.mp4` |
| GF16 | 30 | 30 ✅ | `GF16 20260213 102959-104800.avi` (AVI is fine) |
| GF17 | 30 | 15 | `GF17 20260212 142152-145500.mp4` |
| GF18 | 30 | 15 | `GF18 20260213 102947-104800.mp4` |

## Camera Notes

| Camera | Location | Quality | Notes |
|---|---|---|---|
| GF15 | Main entrance/exit | ✅ Good | 153 plates / 33.5 min. Primary benchmark camera. |
| GF16 | Secondary entrance | ✅ Good | 32 plates / 6.6 min. Clean reads, no fps issue. |
| GF17 | Internal lane (Cargo Lift area) | ⚠️ Poor | 5 plates / 33 min. Low-traffic service zone — reposition recommended. |
| GF18 | Internal lane | ⚠️ Noisy | 64 plates / 18.2 min. Dominated by one parked vehicle (`WB6066`, ~20 OCR variants). |

## Constraints

- Keep `processor.py` as a single runnable script — no async, no task queues
- `app.py` is read-only from DB — never writes
- No defensive try/except unless explicitly requested
- SQLite only — no ORM, no migrations framework
- Always use MP4 for processing — AVI fps headers are unreliable for this camera system
