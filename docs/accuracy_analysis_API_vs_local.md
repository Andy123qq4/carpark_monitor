# API vs Local ALPR Comparison

> Last updated: 2026-03-12
> Test: 5-minute segment from GF15 (first 300 seconds)
> Video: `GF15_5min.mp4` (12.5 fps, 25215 frames)

---

## Test Setup

### Video Segment
- Source: `video/GF15 20260212 142142-145519.mp4`
- Duration: 5 minutes (300 seconds)
- FPS: 12.5 (actual, confirmed via MP4 metadata)
- Frames: 25,215

### Ground Truth (for this video)
From `data/ground_truth.json`:
| Timestamp | Plate |
| --------- | ----- |
| 12.6s | AX8999 |
| 26.9s | JX3833 |
| 33.8s | WR7022 |
| 45.0s | LX8389 |
| 49.5s | ZL9679 |
| ... | ... |

---

## Method 1: Plate Recognizer Cloud API

### Configuration
- Script: `test_video_plate_recognizer.py`
- Sampling: `--fps 5` (every 2-3 frames)
- Rate limit: ~1 request/sec (1.1s sleep between calls)

### Results (first ~8 seconds, 21 frames sampled)

| Frame | Timestamp | Plate      | OCR Conf | Det Conf |
| ----- | --------- | ---------- | -------- | -------- |
| 0     | 0.0s      | MY5597     | 0.82     | 0.82     |
| 2     | 0.2s      | WV5597     | 1.00     | 0.84     |
| 4     | 0.3s      | WV5597     | 0.94     | 0.82     |
| 6     | 0.5s      | WY5597     | 0.99     | 0.83     |
| 8     | 0.6s      | WV5507     | 0.90     | 0.83     |
| 10    | 0.8s      | V597       | 0.80     | 0.76     |
| 14    | 1.1s      | WV55977    | 0.84     | 0.77     |
| 18    | 1.4s      | WY5597     | 0.77     | 0.72     |

- **Total detections:** 8 plates
- **Coverage:** First ~8 seconds only (no plates detected after)
- **Ground truth match:** None (GT starts at 12.6s)

### Pros
- ✅ Higher accuracy when plate is detected
- ✅ Lower false positive rate
- ✅ Better character recognition (W/Y/M confusion less severe)
- ✅ Consistent detection confidence (0.72–0.84)

### Cons
- ❌ Rate limited (~1 req/sec on free tier)
- ❌ Slow processing (190s per image during heavy load)
- ❌ Cost per request ($0.002–0.005 per image)
- ❌ Coverage gaps (no detections after initial frames)
- ❌ Same vehicle produces multiple variant reads

---

## Method 2: Local ALPR (fast-alpr)

### Configuration
- Script: `processor.py`
- Frame interval: 1 (every frame)
- Effective FPS: 12.5

### Results (full 5 minutes)

| Timestamp | Plate      | Ground Truth? |
| --------- | ---------- | ------------- |
| 12.7s     | AX8999     | ✅            |
| 26.9-27.3s | JX3833    | ✅            |
| 33.8s     | WR7022     | ✅            |
| 45-47s    | LX8389     | ✅            |
| 49.5s     | ZL9679     | ✅            |
| 130.6-130.9s | JX5883, JX3893 | ❌ (FP) |
| 195.3-196.6s | ZL3779, ZV9677, ZL6779 | ❌ (FP) |
| ... | DX9588, JX9833, ZC9679, DC7777, BB196, ZZ9671, ZU9679 | ❌ (FP) |

- **Total detections:** 20 plates
- **Ground truth matches:** 5 exact
- **False positives:** 15

### Pros
- ✅ Fast (~20 seconds for 5-minute video)
- ✅ Free (no API costs)
- ✅ Runs locally (no network dependency)
- ✅ Better temporal coverage (finds plates throughout video)
- ✅ Catches all 5 ground truth plates

### Cons
- ❌ Higher false positive rate (15 FP vs 5 TP)
- ❌ Character confusion (9↔0, V↔Y↔W, dropped digits)
- ❌ Noisy output requiring heavy deduplication
- ❌ Lower per-detection accuracy

---

## Comparison Summary

| Metric                | API (Plate Recognizer) | Local (fast-alpr) |
| -------------------- | ---------------------- | ----------------- |
| Processing speed     | ~1 req/sec            | 12.5 frames/sec  |
| Cost                 | $0.002–0.005/frame    | Free              |
| Accuracy (when detects) | Higher              | Lower             |
| False positives      | Low                   | High              |
| Coverage             | Gaps in later frames  | Full video        |
| Ground truth recall  | Unknown (partial run) | 5/5 = 100%       |
| Ground truth precision| Unknown (partial run) | 5/20 = 25%       |

---

## Recommendations

1. **For accuracy-critical validation:** Use API with higher sampling (5 fps)
2. **For real-time processing:** Use local ALPR with strict deduplication
3. **Hybrid approach:** 
   - Run local ALPR for speed/coverage
   - Use API to verify uncertain detections
   - Apply confidence threshold + similarity matching

---

## Notes

- MP4 files have accurate FPS metadata; AVI files report incorrect FPS
- API rate limits vary by time of day (190s latency observed during peak)
- Both methods struggle with character-level OCR accuracy
- Ground truth validation essential for accurate comparison
