# Accuracy Analysis — Camera GF15

## Dataset

| Field | Value |
|---|---|
| Camera | GF15 |
| Video | `GF15 20260212 142142-145519.avi` |
| Duration | 13.9 min |
| Frames scanned | 25,215 (every 5th frame) |
| Total detections saved | 189 |
| Unique plate texts | 162 |

> **No ground truth yet.** Accuracy figures below are observational — true precision/recall require manual verification (Task #6).

---

## Confidence Distribution

| Confidence | Count | % |
|---|---|---|
| 0.95 – 1.00 | 40 | 21% |
| 0.90 – 0.95 | 39 | 21% |
| 0.85 – 0.90 | 28 | 15% |
| 0.80 – 0.85 | 28 | 15% |
| 0.75 – 0.80 | 23 | 12% |
| 0.70 – 0.75 | 26 | 14% |
| < 0.70 | 5 | 3% |

- **Average confidence**: 0.86
- **79% of reads are ≥ 0.80** — generally reliable zone
- 5 reads below 0.70 are likely noise (short/partial plates)

---

## Known Failure Modes

### 1. Length-varying reads (same plate, different char count)

The similarity check (`plates_similar`) requires equal length, so different-length OCR errors form separate clusters.

| Likely same plate | Reads in DB |
|---|---|
| `ZL9679` | `ZL9679` (×5), `ZL967` (×2) |
| `WR7022` | `WR7022` (×3), `WR7922` (×2) |
| `PD6715` | `PD6715` (×2), `PD671` (×2) |

**Root cause**: Model occasionally drops or adds a digit when plate is far/small/angled.

**Fix**: P2 — length-tolerant similarity using edit distance, or regex grammar enforcement.

### 2. Char confusions not in current map

| Observed pair | OCR confusion | In map? |
|---|---|---|
| `AX8999` / `AX0999` | `8` ↔ `0` | ❌ No |
| `ZL9679` / `ZL3679` | `9` ↔ `3` | ❌ No |
| `WR7022` / `MR7022` | `W` ↔ `M` | ❌ No |
| `KN586` / `XN586` | `K` ↔ `X` | ❌ No |

**Fix**: P2 — expand confusion map, or use position-aware HK grammar (`[A-Z]{1,2}[0-9]{1,4}`).

### 3. Same plate, multiple legitimate re-entries

`ZL9679` seen at 18.8s and again at 81.7s — this is a genuine re-entry (same vehicle drove in twice). The tracker correctly stores both as separate events. This is **correct behaviour**, not an error.

---

## Improvement Roadmap

| Priority | Fix | Expected impact |
|---|---|---|
| ✅ P1 | Multi-frame confidence voting | Reduced duplicate rows per pass |
| P2 | HK grammar + expanded confusion map | Merge more same-plate variants |
| P3 | CLAHE preprocessing on crop | Better reads for dark/overexposed plates |
| P4 | Plate Recognizer API trial | Baseline comparison (95%+ claimed) |
| P5 | Fine-tune on HK plates | Only if P1–P4 insufficient |
| #6 | Ground truth + `benchmark.py` | Enable objective metric tracking |

---

## Limitations of This Analysis

- **Single camera angle** (GF15 only) — accuracy may differ significantly at other angles or lighting conditions
- **Single 14-min video** — not representative of night, rain, or high-traffic conditions
- **No ground truth** — all "failure modes" above are inferred from OCR patterns, not verified against real plates
