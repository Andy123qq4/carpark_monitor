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

- **`processor.py`** — CLI batch job. Opens a video, extracts every 5th frame via OpenCV, runs fast-alpr (YOLO v9 + ONNX) to detect plates, validates against HK plate regex (see below), saves crop JPEGs to `data/detections/`, writes rows to SQLite.
- **`dedup.py`** — Post-processing. `TemporalTracker` buffers reads per plate cluster and emits the confidence-voted best text on cluster expiry (P1). `plates_similar()` groups OCR variants using edit distance + confusion map.
- **`db.py`** — Data access layer. `init_db()` creates the table + unique index + runs migrations. `save_detection()` uses `INSERT OR IGNORE` for idempotency. `get_plate_sessions()` uses SQL window functions (LAG → SUM → ROW_NUMBER) to group raw detections into per-plate visits with a 30s gap threshold.
- **`app.py`** — FastAPI server. Single `GET /` endpoint renders `templates/index.html` via Jinja2. Serves crop frames as static files under `/detections/`. Also serves MJPEG clip stream and SSE realtime processing.

**Camera ID** is parsed from the video filename stem (first word before space, e.g. `GF15`).

**File naming**: `data/detections/{camera_id}_{frame_num}_{plate_text}_crop.jpg` (plate crop only — full annotated frames removed).

## ⚠️ AVI FPS Bug + MP4 Conversion

The AVI files from this camera system report **wrong fps in the container header** (all claim 30fps). The actual fps varies per camera and was verified by ffmpeg re-encoding, which reads per-frame timestamps from the stream.

**Policy**: AVI files are kept as raw archive. All processing uses MP4 only. MP4 also decodes ~31% faster than AVI (benchmarked: 1116 vs 850 frames/sec).

Convert with: `ffmpeg -i input.avi -c:v libx264 -crf 18 -preset fast -an output.mp4`

| Camera | AVI claimed fps | Actual fps | Frames (MP4) | MP4 file |
|---|---|---|---|---|
| GF15 | 30 | 12.5 | 25,215 | `GF15 20260212 142142-145519.mp4` |
| GF16 | 30 | ~30 | 32,376 | `GF16 20260213 102959-104800.mp4` |
| GF17 | 30 | 15 | 29,828 | `GF17 20260212 142152-145500.mp4` |
| GF18 | 30 | 15 | ~16,410 | `GF18 20260213 102947-104800.mp4` |

> Actual fps differs per camera because each was configured independently in the DVR. AVI headers are unreliable for this system — always use the MP4.

## Camera Notes

| Camera | Location | Quality | Notes |
|---|---|---|---|
| GF15 | Main entrance/exit | ✅ Good | 153 plates / 33.5 min. Primary benchmark camera. |
| GF16 | Secondary entrance | ✅ Good | 32 plates / 6.6 min. Clean reads, no fps issue. |
| GF17 | Internal lane (Cargo Lift area) | ⚠️ Poor | 5 plates / 33 min. Low-traffic service zone — reposition recommended. |
| GF18 | Internal lane | ⚠️ Noisy | 64 plates / 18.2 min. Dominated by one parked vehicle (`WB6066`, ~20 OCR variants). |

## HK Vehicle Plate Formats

### Standard Private Vehicles (99% of car park traffic)
Format: `XX####` — 2 letters + 1–4 digits (no leading zero)
Examples: `AB 1234`, `WA 9999`, `CD 88`

**Excluded letters in standard plates: I, O, Q** (avoid confusion with 1, 0)
Current series (2026): reverse-alphabetical prefixes (WA, VA, UA…)

### Special / Government Vehicles
| Prefix | Example | Notes |
|---|---|---|
| `A`, `F` | `A123`, `F456` | Ambulance, Fire dept |
| `AM` | `AM789` | Police, Customs, Postal |
| `LC` | `LC1` | Legislative Council |
| `ZG` | `ZG001` | PLA HK Garrison (distinct black/white style) |
| `VV`, `DB` | `VV12`, `DB88` | Village vehicles (Lamma, DB) |

### Cross-Border Plates
| Type | Format | Notes |
|---|---|---|
| Mainland vehicles (港珠澳) | `FT####`, `FU####`, `FV####`, `FW####` | Left-hand drive, standard HK format |
| Macau vehicles | `ZM####`, `ZN####`, `ZP####` | Standard HK format |
| HK vehicles on mainland | `粤Z·XXXX港` | Mainland format — visually completely different, OCR cannot read |

### Personalized Plates (since 2006)
- Up to **8 characters**, letters + digits, no I/O/Q
- Examples: `EMPEROR`, `1LOVEU`, `88888`
- Rare in car parks; too diverse to enumerate

### Historical / Other
- **Digits only** `####`: pre-1959 vehicles (still valid, rarely seen)
- **Trailer suffix** `####T`: number + T (e.g. `1234T`)

### HK Plate Regex in This Codebase
```python
HK_PLATE_RE = re.compile(r'^[A-HJ-NP-Z]{1,2}\s?[0-9]{1,4}$')
```
Excludes I, O, Q from letter prefix. Allows 1–2 letter prefix + 1–4 digits.
Intentionally does NOT cover personalized plates (too many forms → high false positive risk).

### ALPR Notes
- Cross-border `粤Z港` plates are unreadable by the ONNX OCR model (Chinese characters + different font)
- Precision bottleneck is digit OCR errors (`3↔9`, `4↔9`, `6↔7`) — not fixable by regex
- `O3607` (5 digits) was a known garbage detection removed manually; current regex prevents recurrence

## Constraints

- Keep `processor.py` as a single runnable script — no async, no task queues
- `app.py` is read-only from DB — never writes
- No defensive try/except unless explicitly requested
- SQLite only — no ORM, no migrations framework
- Always use MP4 for processing — AVI fps headers are unreliable for this camera system
