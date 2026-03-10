# Accuracy Analysis — All Cameras (Iteration 1, Post-P1)

> Last updated: 2026-03-10
> Algorithm: P1 (multi-frame confidence voting) applied to all cameras.
> No ground truth yet — figures are observational. True precision/recall require Task #6.

---

## Per-Camera Summary

| Camera | Video | Duration | Frames | Detections | Unique Plates | Avg Conf | Min Conf |
|---|---|---|---|---|---|---|---|
| GF15 | GF15 20260212 142142-145519.avi | 13.9 min | 25,215 | 189 | 162 | 0.86 | 0.62 |
| GF16 | GF16 20260213 102959-104800.avi | 6.6 min  | ~11,880 | 32 | 32 | 0.85 | 0.72 |
| GF17 | GF17 20260212 142152-145500.avi | 13.9 min | 29,828 | **7** | 7 | 0.86 | 0.70 |
| GF18 | GF18 20260213 102947-104800.avi | 3.2 min  | 16,410 | 77 | 55 | 0.88 | 0.70 |

**Total across all cameras**: 305 detections, 256 unique plate texts

---

## Per-Camera Analysis

### GF15 — Richest data, most noise

- 189 detections / 162 unique texts in 13.9 min (~13.6 plates/min)
- Highest volume camera — most varied plate angles and distances
- Most OCR noise observed: length-varying reads, char confusions
- Example: `ZL9679` seen 5× (2 genuine visits + length variants `ZL967`)
- **Confidence distribution**:

| Bucket | Count | % |
|---|---|---|
| ≥ 0.95 | 40 | 21% |
| 0.90–0.95 | 39 | 21% |
| 0.85–0.90 | 28 | 15% |
| 0.80–0.85 | 28 | 15% |
| 0.75–0.80 | 23 | 12% |
| 0.70–0.75 | 26 | 14% |
| < 0.70 | 5 | 3% |

---

### GF16 — Clean, low volume

- 32 detections / 32 unique plates in 6.6 min (~4.8 plates/min)
- All detections are unique texts — no apparent duplicates
- Confidence floor 0.72 — no very-low-confidence noise
- Likely a lower-traffic or more distant camera angle

---

### GF17 — ⚠️ Suspected poor camera angle

- Only **7 plates in 13.9 min** (0.5 plates/min) — same duration as GF15 which got 189
- All 7 detections clustered at ~90–91s and ~835s
- Mostly variants of `ZL9679` (same plate as seen by GF15 at the same time ~90s)
  - `ZL9679` (1.00), `LL9679` (0.94), `ZL977`, `ZL679`, `ZL4779`, `DL9774` — heavily noisy
- **Root cause hypotheses**: camera pointing at a distant/narrow lane, bad lighting, or obstructed view
- **Action needed**: physically inspect GF17 camera angle before using data for ground truth

---

### GF18 — ⚠️ Same plate stuck in frame

- 77 detections but only 55 unique texts in 3.2 min
- ~22 duplicate-text events — all variants of what is almost certainly **`WB6066`**
  - Seen as: `WB6066`, `WB0066`, `AB6066`, `MB6066`, `WB6006`, `WB6060`, `WB0060`, etc. (20+ variants)
- Plate appears for long durations at close range (bboxes 47–67px wide at rows 800–1000)
  - Likely a **parked or slowly moving vehicle** directly in camera view
- `VH703` (1.00), `VH763` (0.98) — clean reads for a separate vehicle
- **Insight**: P2 (char correction) + length-tolerant similarity would collapse most `WB6066` variants into 1–2 rows

---

## Known Failure Modes

### 1. Length-varying reads

`plates_similar()` requires equal length — different-length OCR errors form separate clusters.

| Likely true plate | DB variants observed |
|---|---|
| `ZL9679` | `ZL9679`, `ZL967`, `ZL679`, `ZL977`, `ZL4779` |
| `WB6066` | `WB6066`, `WB0066`, `WB6006`, `WB6060`, `WB606`, `AB6066`, `MB6066`, ... |
| `WR7022` | `WR7022`, `WR7922`, `MR7022` |

**Fix**: P2 — Levenshtein distance ≤ 1 for same-prefix plates, or HK grammar enforcement.

### 2. Char confusions not in current map

| Observed pair | Confusion | In map? |
|---|---|---|
| `WB6066` / `MB6066` | `W` ↔ `M` | ❌ |
| `WB6066` / `AB6066` | `W` ↔ `A` | ❌ |
| `WB6066` / `WB0066` | `6` ↔ `0` | ❌ |
| `AX8999` / `AX0999` | `8` ↔ `0` | ❌ |
| `ZL9679` / `ZL3679` | `9` ↔ `3` | ❌ |

**Fix**: P2 — expand confusion map: add `W↔M↔N↔H`, `6↔0↔8`, `9↔3`.

### 3. GF17 near-zero detections

Camera produces almost no valid reads. Either mechanical issue or poor placement.

---

## Improvement Roadmap

| Task | Fix | Status |
|---|---|---|
| P1 | Multi-frame confidence voting | ✅ Done |
| P2 | HK grammar + expanded confusion map + length tolerance | Pending |
| P3 | CLAHE preprocessing on crops | Pending |
| P4 | Plate Recognizer API trial | Pending |
| P5 | Fine-tune on HK plates | Pending |
| #6 | Ground truth + `benchmark.py` | Pending — needed before P2 measurement |

---

## Limitations

- **No ground truth** — all failure modes are inferred, not verified
- **GF17 data is unreliable** — investigate camera before including in benchmark
- **GF18 dominated by one parked vehicle** — not representative of typical traffic
- **Single day of footage per camera** — does not capture night, rain, or rush-hour conditions
