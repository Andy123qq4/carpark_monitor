# P3: CLAHE Preprocessing — Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to plate crops before OCR, reducing digit/letter misreads and improving Precision from ~24% toward 50%+.

**Architecture:** In `detection.py`, replace the single `self.alpr.predict(frame)` call with a two-stage pipeline: (1) `self.alpr.detector.predict(frame)` for bbox detection, (2) extract crop → apply CLAHE → `self.alpr.ocr.predict(crop)` for OCR. Reconstruct `ALPRResult` manually. No changes to `processor.py`, `dedup.py`, or DB.

**Tech Stack:** Python 3.10, OpenCV (`cv2.createCLAHE`), `fast_alpr` internal API (`ALPR.detector`, `ALPR.ocr`)

---

## Context

**Problem:** GF15 benchmark shows Precision=24%, Recall=79%. The 73 FP sessions are OCR variants of real plates (`ZL9679` → `ZL3679`, `ZL4679`, `ZI9679`). These digit substitutions (`3↔9`, `4↔9`) occur because plate crops are low-contrast — the OCR model misreads digits consistently.

**Why CLAHE:** Adaptive histogram equalization normalizes local contrast, making digit strokes sharper and more distinct. It operates per-tile (8×8 default), so it handles non-uniform lighting across the plate.

**Hook point in fast_alpr:**
```python
# fast_alpr/alpr.py ALPR.predict() internals (read-only, don't modify):
plate_detections = self.detector.predict(img)
for detection in plate_detections:
    bbox = detection.bounding_box  # .x1, .y1, .x2, .y2
    cropped_plate = img[y1:y2, x1:x2]        # ← CLAHE goes here
    ocr_result = self.ocr.predict(cropped_plate)
    alpr_results.append(ALPRResult(detection=detection, ocr=ocr_result))
```

We replicate this loop in `detection.py` with CLAHE inserted between crop extraction and OCR.

---

## Implementation Steps

### Step 1 — Add `_apply_clahe(crop)` helper to `detection.py`

- [ ] Import `ALPRResult` from `fast_alpr` (or reconstruct compatible namedtuple — check import)
- [ ] Add module-level CLAHE instance: `_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))`
- [ ] Add helper:

```python
def _apply_clahe(crop: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = _CLAHE.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
```

**Why LAB colorspace:** Apply CLAHE only to the L (luminance) channel, leaving color unchanged. Avoids color distortion on yellow HK plates.

### Step 2 — Replace `alpr.predict()` with two-stage pipeline in `detect_frame()`

- [ ] In `ALPRDetector.detect_frame()`, replace:
  ```python
  results = self.alpr.predict(frame)
  ```
  with:
  ```python
  results = _predict_with_clahe(self.alpr, frame)
  ```

- [ ] Add `_predict_with_clahe(alpr, frame)` function:
  ```python
  def _predict_with_clahe(alpr, frame: np.ndarray):
      from fast_alpr.alpr import ALPRResult
      plate_detections = alpr.detector.predict(frame)
      out = []
      for detection in plate_detections:
          bbox = detection.bounding_box
          x1, y1 = max(int(bbox.x1), 0), max(int(bbox.y1), 0)
          x2, y2 = min(int(bbox.x2), frame.shape[1]), min(int(bbox.y2), frame.shape[0])
          crop = frame[y1:y2, x1:x2]
          if crop.size > 0:
              crop = _apply_clahe(crop)
          ocr_result = alpr.ocr.predict(crop)
          out.append(ALPRResult(detection=detection, ocr=ocr_result))
      return out
  ```

### Step 3 — Verify on a sample frame

- [ ] Run processor on a single short clip and confirm output looks reasonable:
  ```bash
  python processor.py "video/GF15 20260212 142142-145519.avi" --max-frames 500
  ```
- [ ] Spot-check: crop images in `data/detections/` should look sharpened, not over-processed
- [ ] Confirm no crash on empty crops (`crop.size > 0` guard)

### Step 4 — Re-run benchmark

- [ ] Wipe GF15 detections and reprocess full video:
  ```bash
  sqlite3 data/carpark.db "DELETE FROM detections WHERE video_file LIKE 'GF15%';"
  python processor.py "video/GF15 20260212 142142-145519.avi"
  ```
- [ ] Open `/benchmark` and record new Precision/Recall/F1
- [ ] Update `docs/accuracy_analysis_P3_benchmark.md` with results

---

## Tuning Parameters (if Step 4 results are poor)

| Parameter | Default | Try if over-enhanced | Try if under-enhanced |
|---|---|---|---|
| `clipLimit` | 2.0 | 1.0 | 3.0–4.0 |
| `tileGridSize` | (8,8) | (4,4) | (16,16) |

**Signs of over-enhancement:** OCR confidence drops, more noise characters appear in plate text.
**Signs of under-enhancement:** No improvement vs baseline.

---

## Success Criteria

- [ ] Precision improves from 24% (baseline) — target ≥ 40%
- [ ] Recall stays ≥ 79% (must not regress)
- [ ] No new crashes or empty-result frames
- [ ] `ALPRResult` reconstruction is compatible with existing `detect_frame()` result parsing

---

## Files Changed

| File | Change |
|---|---|
| `detection.py` | Add `_CLAHE`, `_apply_clahe()`, `_predict_with_clahe()`; replace `alpr.predict()` call |
| `docs/accuracy_analysis_P3_benchmark.md` | Add post-P3 benchmark results |

**No other files change.** `processor.py`, `dedup.py`, `db.py`, `app.py` untouched.
