# Accuracy Analysis — All Cameras (Iteration 1, Post-P1)

> Last updated: 2026-03-10
> Algorithm: P1 (multi-frame confidence voting) applied to all cameras.
> No ground truth yet — figures are observational. True precision/recall require Task #6.

---

## ⚠️ AVI FPS Bug (Fixed)

All cameras except GF16 had wrong fps in the AVI container header. The processor was calculating timestamps incorrectly. **All affected cameras converted to MP4 via ffmpeg.**

| Camera | AVI claimed | Actual fps | Timestamp error | Fix |
|---|---|---|---|---|
| GF15 | 30 fps | 12.5 fps | 2.4× too small | Converted to MP4 |
| GF16 | 30 fps | 30 fps | ✅ None | N/A |
| GF17 | 30 fps | 15 fps | 2× too small | Converted to MP4 |
| GF18 | 30 fps | 15 fps | 2× too small | Converted to MP4 |

---

## Per-Camera Summary

| Camera | Video (MP4) | Duration | Frames | Detections | Unique Plates | Avg Conf |
|---|---|---|---|---|---|---|
| GF15 | GF15 20260212 142142-145519.mp4 | 33.5 min | 25,215 | 153 | 152 | 0.87 |
| GF16 | GF16 20260213 102959-104800.avi | 6.6 min | 32,376 | 32 | 32 | 0.85 |
| GF17 | GF17 20260212 142152-145500.mp4 | 33.1 min | 29,828 | 5 | 5 | 0.87 |
| GF18 | GF18 20260213 102947-104800.mp4 | 18.2 min | 16,410 | 64 | 46 | 0.89 |

**Total**: 254 detections, 235 unique plate texts across 4 cameras

---

## Per-Camera Analysis

### GF15 — Main entrance/exit, best data

- 153 detections / 152 unique texts in 33.5 min (~4.6 plates/min)
- Good variety of vehicles and angles
- Primary camera for benchmarking

### GF16 — Clean, moderate traffic

- 32 detections / 32 unique plates in 6.6 min (~4.8 plates/min)
- All detections are unique texts — no apparent duplicates
- AVI fps is correct (30fps) — no conversion needed
- Reliable secondary benchmark source

### GF17 — ⚠️ Wrong camera placement

- Only **5 plates in 33 min** (0.15 plates/min)
- Camera monitors internal carpark lanes near **Cargo Lift** — low-traffic service area
- Even with full video, too sparse for benchmarking
- **Recommendation**: Reposition camera to entrance/exit gate

### GF18 — Parked vehicle dominates frame

- 64 detections / 46 unique texts in 18.2 min
- Detections concentrated in first ~6 min — mostly variants of **`WB6066`** (parked vehicle)
- `WB6066` appears as: `WB0066`, `AB6066`, `MB6066`, `WB6006`, `WB6060`, etc. (~20 variants)
- P2 (expanded confusion map + length tolerance) would collapse most of these
- **Recommendation**: Use Task #8 (stationary plate filter) before including in benchmark

---

## Known Failure Modes

### 1. Length-varying reads

`plates_similar()` requires equal length — different-length OCR errors form separate clusters.

| Likely true plate | DB variants observed |
|---|---|
| `ZL9679` | `ZL9679`, `ZL967`, `ZL679`, `ZL977`, `ZL4779` |
| `WB6066` | `WB6066`, `WB0066`, `WB6006`, `WB6060`, `WB606`, `AB6066`, `MB6066`, ... |

**Fix**: P2

### 2. Char confusions not in current map

| Observed pair | Confusion | In map? |
|---|---|---|
| `WB6066` / `MB6066` | `W` ↔ `M` | ❌ |
| `WB6066` / `AB6066` | `W` ↔ `A` | ❌ |
| `WB6066` / `WB0066` | `6` ↔ `0` | ❌ |
| `AX8999` / `AX0999` | `8` ↔ `0` | ❌ |

**Fix**: P2

### 3. Stationary vehicles

GF18's `WB6066` (parked car) generates ~20 noisy rows over several minutes.

**Fix**: Task #8 — filter plates seen in same bbox region for > N seconds

---

## Improvement Roadmap

| Task | Fix | Status |
|---|---|---|
| P1 | Multi-frame confidence voting | ✅ Done |
| AVI fps bug | Convert broken AVIs to MP4 | ✅ Fixed |
| P2 | HK grammar + expanded confusion map + length tolerance | Pending |
| P3 | CLAHE preprocessing on crops | Pending |
| P4 | Plate Recognizer API trial | Pending |
| P5 | Fine-tune on HK plates | Pending |
| #6 | Ground truth + `benchmark.py` | Pending |
| #7 | GF17 camera investigation | ✅ Done — reposition recommended |
| #8 | Filter stationary/parked plates | Pending |

---

## Limitations

- **No ground truth** — failure modes are inferred, not verified
- **GF17 unusable** for benchmarking until camera is repositioned
- **GF18 skewed** by one parked vehicle until #8 is implemented
- **Single day of footage** — does not capture night, rain, or rush-hour
