# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

**Sinovation 2026 Competition** — Team 8 building AI-powered car park monitoring for China Hong Kong City (CHKC, 中港城), TST.

- **Deadline:** 2026-04-30 (3-5 min video + 15-page deck + prototype)
- **Judging:** Feasibility 30%, Cost-effectiveness 30%, Innovativeness 30%, Presentation 10%, Teamwork bonus 10%
- **Budget:** HK$27,500 per team (spent ~HK$2,080 so far)

### The Problem

CHKC's loading bay **cannot install barriers** (fire safety). Two security guards work 24/7 shifts (HK$20K/month each = HK$480K/year) to manually time trucks and collect overtime fees. 20-minute free parking, then charged per occurrence.

### Solution Strategy (Kenneth Leung Framework)

This is a **business workflow problem, not just a coding problem**. Workflow first, then automate:

1. **Registration mandate** — force vehicles to register (plate + payment) via app or on-site
2. **AI automation** — ALPR detects plate → DB lookup → auto-log time → auto-charge or alert
3. **Progressive human reduction** — fewer unregistered vehicles over time → less staff needed
4. **Data analytics** — parking duration, repeat offenders, peak patterns

### User Persona

| Field | Detail |
|---|---|
| **Who** | CHKC property management (Sino Group) — non-technical, care about cost savings |
| **Job-to-be-Done** | Reduce HK$480K/year security cost while maintaining fee collection |
| **Context** | Commercial loading bay, trucks come and go, no barriers possible |
| **Success criteria** | Working demo that shows: detect → track → alert → report flow |

## Commands

```bash
# Run the plate processor — hybrid mode (recommended: local YOLO + API OCR on best crops)
python3 processor.py "video/GF15 20260212 142142-145519.mp4" --backend hybrid

# Run with local-only ALPR (fast, free, lower accuracy)
python3 processor.py "video/GF15 20260212 142142-145519.mp4" --backend fast_alpr

# Start the dashboard web server
uvicorn app:app --reload
```

## Architecture

**Two-process system** — processor and web server are decoupled, communicating only via SQLite.

```mermaid
graph LR
    CCTV[CCTV MP4] --> Processor[processor.py]
    Processor --> |YOLO detect| Detection[detection.py]
    Detection --> Dedup[dedup.py]
    Dedup --> |best crop per car| API[Plate Recognizer API]
    API --> DB[(SQLite)]
    DB --> App[app.py FastAPI]
    App --> Dashboard[Web Dashboard]
```

- **`processor.py`** — CLI batch job. Opens a video, runs detection per frame, deduplicates, saves crop JPEGs + writes to SQLite. Supports `--backend {fast_alpr,plate_recognizer,hybrid}`. **Hybrid mode (recommended):** local YOLO detects plates → `TemporalTracker` groups duplicates within 3s window → picks best crop by visual quality → sends only the best wide crop to Plate Recognizer API. Reduces API calls from hundreds to ~24 per 33-min video.
- **`detection.py`** — Detector abstraction. `ALPRDetector` (local YOLO v9 + ONNX OCR), `PlateRecognizerDetector` (cloud API on full frames), and `recognize_crop()` (sends a single plate crop to API for OCR — used by hybrid mode). Wide crops (100px padding around plate bbox) are required for `recognize_crop()` because the API needs surrounding context to detect plates.
- **`dedup.py`** — Post-processing. `TemporalTracker` buffers reads per plate cluster and emits the best result on cluster expiry. Matching criteria: `plates_similar()` (edit distance + confusion map) OR `bbox_iou > 0.3` OR **temporal proximity (within 3 seconds)**. The 3s window handles moving vehicles where bbox IoU drops and OCR text varies frame-to-frame. `crop_quality_score()` selects the sharpest, largest crop for API submission.
- **`db.py`** — Data access layer. `init_db()` creates the table + unique index + runs migrations. `save_detection()` uses `INSERT OR IGNORE` for idempotency. `get_plate_sessions()` uses SQL window functions (LAG → SUM → ROW_NUMBER) to group raw detections into per-plate visits with a 30s gap threshold.
- **`app.py`** — FastAPI server. Single `GET /` endpoint renders `templates/index.html` via Jinja2. Serves crop frames as static files under `/detections/`. Also serves MJPEG clip stream and SSE realtime processing.

**Camera ID** is parsed from the video filename stem (first word before space, e.g. `GF15`).

**File naming**: `data/detections/{camera_id}_{frame_num}_{plate_text}_crop.jpg`. In hybrid mode, crops include 100px surrounding context (wide crop); in fast_alpr mode, crops are tight (4px padding).

## AVI FPS Bug + MP4 Conversion

AVI files from this camera system report **wrong fps in the container header** (all claim 30fps). Actual fps varies per camera.

**Policy**: AVI = raw archive. All processing uses MP4 only. MP4 decodes ~31% faster than AVI.

Convert: `ffmpeg -i input.avi -c:v libx264 -crf 18 -preset fast -an output.mp4`

| Camera | AVI claimed fps | Actual fps | Frames (MP4) | MP4 file |
|---|---|---|---|---|
| GF15 | 30 | 12.5 | 25,215 | `GF15 20260212 142142-145519.mp4` |
| GF16 | 30 | ~30 | 32,376 | `GF16 20260213 102959-104800.mp4` |
| GF17 | 30 | 15 | 29,828 | `GF17 20260212 142152-145500.mp4` |
| GF18 | 30 | 15 | ~16,410 | `GF18 20260213 102947-104800.mp4` |

## Camera Notes

| Camera | Location | Quality | Notes |
|---|---|---|---|
| GF15 | Main entrance/exit | Good | 24 unique plates / 33.5 min (hybrid mode). Primary benchmark. |
| GF16 | Secondary entrance | Good | 32 plates / 6.6 min. Clean reads. |
| GF17 | Internal lane (Cargo Lift) | Poor | 5 plates / 33 min. Reposition recommended. |
| GF18 | Internal lane | Noisy | 64 plates / 18.2 min. Dominated by parked WB6066. |

## ALPR Accuracy Status

| Iteration | Change | GF15 Precision | GF15 Recall | GF15 F1 |
|---|---|---|---|---|
| P1 | Confidence voting | — | — | — |
| P2 | Confusion map + length tolerance | 24% | 79% | 37% |
| P3 | CLAHE preprocessing | 26% | 66% | 37% |
| Baseline | Overall (all cameras) | 30% | 77% | 43% |
| **P4** | **Hybrid: local YOLO + 3s dedup + API OCR** | — | — | — |

### P4 Hybrid Pipeline Results (GF15, 33.5 min video)

| Metric | Before (fast_alpr) | After (hybrid) |
|---|---|---|
| Detections emitted | 62 | **24** (3s temporal dedup) |
| API calls | 0 | **20** (4 fell back to local) |
| Visually verified correct | 15/24 (63%) | **~17/24 (71%+)** |

**Key improvements:**
- 3s temporal window reduced 62 → 24 detections (same car no longer emits 4+ times)
- API fixes local OCR letter errors: XL→YL, YX→YA, KR→WR, LA9228→LA3028
- Wide crop extraction (100px padding) required — tight crops fail API detection
- 4 local fallbacks: 2 non-standard plates (cross-border 粤Z, 2-line), 2 too blurry

**Remaining limitations:**
- Cross-border 粤Z plates: Chinese characters, not readable by either OCR
- Very small/distant plates: both local and API fail
- Letter ambiguity (V/Y, S/5): sometimes neither OCR resolves correctly

## HK Vehicle Plate Formats

### Standard Private Vehicles (99% of car park traffic)
Format: `XX####` — 2 letters + 1–4 digits (no leading zero)
Examples: `AB 1234`, `WA 9999`, `CD 88`

**Excluded letters in standard plates: I, O, Q** (avoid confusion with 1, 0)

### HK Plate Regex in This Codebase
```python
HK_PLATE_RE = re.compile(r'^[A-HJ-NP-Z]{1,2}\s?[0-9]{1,4}$')
```
Excludes I, O, Q. Allows 1–2 letter prefix + 1–4 digits. Does NOT cover personalized plates.

### Cross-Border / Special Plates
- Cross-border `粤Z港` plates: unreadable by ONNX OCR (Chinese characters)
- Government/special: `A/F` (emergency), `AM` (police), `LC` (LegCo), `ZG` (PLA)
- Personalized: up to 8 chars, too diverse to regex

## CHKC Infrastructure

- **CCTV:** Bosch (NUV-3702, NBE-3502, NDE-8504 8MP, NDP-5512 PTZ, NDV-3503, NDS-5704 360) + Sony (SNC-XM631, SNC-EB632R, SNC-VM772R, WR632C)
- **NVR:** VidoNet (8/16/32ch with Face Recognition)
- **VMS:** iNEX Video Management System
- **Network:** Allied Telesis PoE + L3 managed switches

## Constraints

- Keep `processor.py` as a single runnable script — no async, no task queues
- `app.py` is read-only from DB — never writes
- No defensive try/except unless explicitly requested
- SQLite only — no ORM, no migrations framework
- Always use MP4 for processing — AVI fps headers are unreliable
- **MINIMIZE time spent** — focus on high-impact items only, don't drill down on minor details
