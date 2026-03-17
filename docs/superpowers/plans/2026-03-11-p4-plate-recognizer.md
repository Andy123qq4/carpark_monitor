# P4: Plate Recognizer API Trial — Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fast-alpr's ONNX OCR stage with Plate Recognizer's cloud API to improve OCR accuracy on HK plates. Measure whether Precision improves from 30% toward 60%+, with Recall staying ≥ 77%.

**Architecture:** Add a new `PlateRecognizerDetector` class in `detection.py` that implements the same `detect_frame()` interface as `ALPRDetector`. Swap it in `processor.py` via an env var / CLI flag. No changes to `dedup.py`, `db.py`, or `app.py`. After benchmarking, decide whether to keep or revert.

**Tech Stack:** Python 3.10, `requests`, Plate Recognizer Cloud API (https://api.platerecognizer.com/v1/plate-reader/), OpenCV for frame encoding.

---

## Context

### Why P4

Current bottleneck (from benchmark analysis):
- **Precision 30%** — same vehicle produces 3–6 OCR variant sessions (`ZL9679` → `ZL3779`, `ZL6779`, `ZU9679`, `ZZ9671`, `ZV9677`)
- **Root cause:** ONNX OCR model misreads digits (`3↔9`, `4↔9`, `6↔7`) — not fixable by CLAHE (P3) or confusion map expansion
- **P3 result:** neutral — CLAHE helped some crops, hurt others. No meaningful improvement.

Plate Recognizer is trained on real-world plates globally, with an HK region hint (`regions=["hk"]`), which specifically improves `0/O` and `1/I` disambiguation.

### Baseline (to beat)
| Camera | P | R | F1 | GT | Det |
|---|---|---|---|---|---|
| GF15 | 27% | 73% | 40% | 22 | 59 |
| GF16 | 27% | 75% | 40% | 4 | 11 |
| GF17 | 50% | 100% | 67% | 2 | 4 |
| GF18 | 50% | 100% | 67% | 2 | 4 |
| **Overall** | **30%** | **77%** | **43%** | **30** | **78** |

### API Details
- **Endpoint:** `POST https://api.platerecognizer.com/v1/plate-reader/`
- **Auth:** `Authorization: Token {API_TOKEN}`
- **Image input:** multipart `upload` field (raw JPEG bytes — no disk write needed)
- **HK region hint:** `data={"regions": "hk"}`
- **Response key fields:** `results[].plate` (text), `results[].score` (OCR conf), `results[].dscore` (detection conf), `results[].box` (xmin/ymin/xmax/ymax)
- **Free tier:** 2,500 lookups/month, 1 req/sec rate limit
- **Credit budget:** GF15 at 1fps = ~2040 calls. Covers ~1 full video per month.

---

## Pre-requisites

- [ ] Sign up at https://platerecognizer.com and get API token
- [ ] Set env var: `export PLATE_RECOGNIZER_API=your_token_here`
- [ ] `pip install requests` (already available, but confirm)

---

## Implementation Steps

### Step 1 — Add `PlateRecognizerDetector` to `detection.py`

- [ ] Add import: `import requests`
- [ ] Add env var reader at module level:
  ```python
  PLATE_RECOGNIZER_TOKEN = os.environ.get("PLATE_RECOGNIZER_API", "")
  PLATE_RECOGNIZER_URL = "https://api.platerecognizer.com/v1/plate-reader/"
  ```
- [ ] Add class `PlateRecognizerDetector` with same interface as `ALPRDetector`:
  ```python
  class PlateRecognizerDetector:
      def __init__(self, min_confidence: float = MIN_CONFIDENCE, frame_interval: int = FRAME_INTERVAL):
          self.min_confidence = min_confidence
          self.frame_interval = frame_interval
          self._tracker = dedup.TemporalTracker()
          if not PLATE_RECOGNIZER_TOKEN:
              raise RuntimeError("PLATE_RECOGNIZER_API env var not set")

      def detect_frame(self, frame) -> list[tuple[str, float, tuple]]:
          _, jpg = cv2.imencode(".jpg", frame)
          resp = requests.post(
              PLATE_RECOGNIZER_URL,
              files={"upload": jpg.tobytes()},
              data={"regions": "hk"},
              headers={"Authorization": f"Token {PLATE_RECOGNIZER_TOKEN}"},
              timeout=10,
          )
          resp.raise_for_status()
          detections = []
          for r in resp.json().get("results", []):
              text = r["plate"].upper().strip()
              conf = r["score"]
              if conf < self.min_confidence:
                  continue
              if not HK_PLATE_RE.match(text):
                  continue
              box = r.get("box", {})
              bbox = None
              if box:
                  x1, y1, x2, y2 = box["xmin"], box["ymin"], box["xmax"], box["ymax"]
                  bbox = (x1, y1, x2 - x1, y2 - y1)
              detections.append((text, conf, bbox))
          detections = dedup.apply_confidence_threshold(detections, self.min_confidence)
          detections = dedup.deduplicate_detections(detections)
          return detections
  ```

### Step 2 — Add `--backend` flag to `processor.py`

- [ ] Read current `processor.py` to find the `ALPRDetector()` instantiation
- [ ] Add CLI arg: `--backend {fast_alpr,plate_recognizer}` (default: `fast_alpr`)
- [ ] Instantiate the correct detector class based on flag:
  ```python
  if args.backend == "plate_recognizer":
      detector = detection.PlateRecognizerDetector()
  else:
      detector = detection.ALPRDetector()
  ```
- [ ] Add rate limiting for Plate Recognizer (1 req/sec max):
  ```python
  import time
  # inside frame loop, after detect_frame():
  if args.backend == "plate_recognizer":
      time.sleep(1.0)
  ```

### Step 3 — Test with a short clip first (save credits)

- [ ] Process only the first 60 seconds of GF16 (fewest frames, 4 GT plates):
  ```bash
  # Extract 60s clip
  ffmpeg -i "video/GF16 20260213 102959-104800.mp4" -t 60 -c copy /tmp/gf16_60s.mp4

  # Run with plate_recognizer backend
  PLATE_RECOGNIZER_API=xxx python processor.py /tmp/gf16_60s.mp4 --backend plate_recognizer
  ```
- [ ] Check SQLite output: `sqlite3 data/carpark.db "SELECT plate_text, confidence FROM detections WHERE video_file LIKE '%gf16_60s%'"`
- [ ] Manually compare to GF16 GT: `VD4828`, `PJ1685`, `UN8208`, `VH703`

### Step 4 — Full benchmark run (all 4 videos)

**Credit estimate:** GF15(~2040) + GF16(~396) + GF17(~1790) + GF18(~982) ≈ 5,200 calls
⚠️ **Exceeds free tier (2,500/month)**. Options:
- A) Run GF15 + GF16 only (most representative: ~2,436 calls, fits free tier)
- B) Upgrade to paid plan ($9/month for 10,000 calls)
- C) Sample every 2nd frame (`FRAME_INTERVAL=2`) to halve calls

**Recommended: Option A** — wipe GF15 + GF16, reprocess with plate_recognizer backend:
```bash
sqlite3 data/carpark.db "DELETE FROM detections WHERE video_file IN ('GF15 20260212 142142-145519.mp4','GF16 20260213 102959-104800.mp4');"
PLATE_RECOGNIZER_API=xxx python processor.py "video/GF15 20260212 142142-145519.mp4" --backend plate_recognizer
PLATE_RECOGNIZER_API=xxx python processor.py "video/GF16 20260213 102959-104800.mp4" --backend plate_recognizer
```

### Step 5 — Re-run benchmark and document

- [ ] Open `/benchmark` — record new Precision/Recall/F1 for GF15 and GF16
- [ ] Compare vs baseline in `docs/superpowers/plans/`
- [ ] Update `docs/accuracy_analysis_P3_benchmark.md` with P4 results section
- [ ] **Decision gate**: if Precision ≥ 50% → P4 is adopted as primary backend; if < 40% → revert to fast-alpr

---

## Rollback Plan

If P4 underperforms:
```bash
sqlite3 data/carpark.db "DELETE FROM detections WHERE video_file IN (...);"
python processor.py "video/GF15 ..." --backend fast_alpr   # default, no token needed
```
`PlateRecognizerDetector` stays in `detection.py` (cost = 0 lines), just not used.

---

## Success Criteria

| Metric | Baseline | Target |
|---|---|---|
| Overall Precision | 30% | ≥ 50% |
| Overall Recall | 77% | ≥ 77% (must not regress) |
| Overall F1 | 43% | ≥ 60% |

---

## Files Changed

| File | Change |
|---|---|
| `detection.py` | Add `PlateRecognizerDetector` class, `PLATE_RECOGNIZER_API` env var |
| `processor.py` | Add `--backend` CLI flag, rate-limit for plate_recognizer |
| `docs/accuracy_analysis_P3_benchmark.md` | Add P4 results section |

**No schema changes. No changes to `dedup.py`, `db.py`, `app.py`.**
