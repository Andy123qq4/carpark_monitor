# Accuracy Analysis — All Cameras (Iteration 2, Post-P2)

> Last updated: 2026-03-11
> Algorithm: P2 applied on top of P1 — expanded confusion map, Levenshtein length tolerance, position-aware plate normalization.
> No ground truth yet — figures are observational. True precision/recall require Task #6.

---

## Changes from P1 → P2

| Change | Detail |
|---|---|
| Confusion map expanded | Added: `W↔M`, `W↔N`, `6↔0`, `8↔0`, `7↔Z` |
| Length-tolerant grouping | `plates_similar()` now uses Levenshtein ≤ 2 (was same-length only) |
| Position-aware normalization | `normalize_plate()` corrects digit-in-letter-position (e.g. `8→B`) and letter-in-digit-position (e.g. `B→8`) before saving to DB |

---

## Per-Camera Summary

| Camera | Video (MP4) | Duration | Detections | Unique Plates | Avg Conf | P1 Detections | Δ |
|---|---|---|---|---|---|---|---|
| GF15 | GF15 20260212 142142-145519.mp4 | 33.5 min | 98 | 97 | 0.87 | 153 | -36% |
| GF16 | GF16 20260213 102959-104800.mp4 | 6.6 min | 14 | 13 | 0.90 | 32 | -56% |
| GF17 | GF17 20260212 142152-145500.mp4 | 27.9 min | 4 | 4 | 0.90 | 5 | -20% |
| GF18 | GF18 20260213 102947-104800.mp4 | 6.3 min | 22 | 15 | 0.91 | 64 | -66% |

**Total**: 138 detections, 129 unique plate texts (vs 254 / 235 in P1)

---

## Per-Camera Analysis

### GF15 — Main entrance/exit

- 98 detections / 97 unique in 33.5 min (~2.9 plates/min, down from 4.6)
- Reduction reflects correct merging of OCR variants (e.g. `ZL967` + `ZL9679` → single cluster)
- Still 2 rows with same plate text (`98 - 97 = 1 duplicate`) — likely same car entering twice

### GF16 — Secondary entrance

- 14 detections / 13 unique in 6.6 min (~2.1 plates/min, down from 4.8)
- 56% drop warrants attention. From the processing log:
  - `VD4828`, `YD4828`, `WD4828`, `ND4882` all appear within 0.6s at ~90s — same car, 4 separate rows
  - Root cause: `V↔Y` and `V↔W` not in confusion map (V maps to A/N/B/H/M but not Y/W)
  - **Recommendation**: Add `V↔Y↔W` confusions to P3 map (or treat as P2 follow-up)
- Remaining 10 distinct plates appear at 90s and 362–397s — plausibly 2 clusters of vehicles

### GF17 — Internal lane (Cargo Lift area)

- 4 detections / 4 unique in 27.9 min — unchanged from P1 (5→4)
- Camera placement remains the primary bottleneck

### GF18 — Best improvement

- 22 detections / 15 unique in 6.3 min (was 64 / 46)
- `WB6066` cluster reduced: previously ~20 rows, now 5 rows (5 distinct passes of parked vehicle)
- Remaining `WB6066` variants still separate (`MD6066`, `WG6066`, `AB6066`, `HB6066`):
  - `MD6066`: `W↔M` ✅ in map — but `levenshtein(WB6066, MD6066)=2`, diffs=(W→M, B→D), `char_similarity(B, D)=False` → not merged
  - `WG6066`: `B↔G` — G is not B-confusable → not merged
  - `AB6066`: `W↔A` — not in map → not merged
  - These are second-order confusions requiring P3

---

## Remaining Failure Modes

### 1. V↔Y↔W not fully mapped

`V` maps to `A/N/B/H/M` but `Y` and `W` are missed. GF16's `VD4828/YD4828/WD4828` cluster is the clearest example.

**Fix**: Add `Y: 'V'` and extend `V: 'ANBHMY'`, `W: 'MNV'` (or scope to P3).

### 2. Second-position letter confusions

`WB6066 → MD6066`: `W↔M` (fixed) but `B↔D` is not confusable → cluster rejected.
`WB6066 → WG6066`: `B↔G` not confusable → separate cluster.

These require expanding the `B/D/G` confusion group.

### 3. Length tolerance may be over-merging GF16

GF16 went 32→14 (56%). Without ground truth we cannot confirm this is all correct deduplication. **Task #6 (ground truth benchmark) needed to verify.**

### 4. Stationary vehicle still generating rows

`WB6066` now appears 5 times in GF18 (vs ~20 in P1) — good improvement, but Task #8 (bbox velocity filter) would reduce this to 1.

---

## Improvement Roadmap

| Task | Fix | Status |
|---|---|---|
| P1 | Multi-frame confidence voting | ✅ Done |
| P2 | Expanded confusion map + length tolerance + normalize_plate | ✅ Done |
| P2b | Add V↔Y↔W, B↔D↔G confusions | Pending |
| P3 | CLAHE preprocessing on crops | Pending |
| P4 | Plate Recognizer API trial | Pending |
| P5 | Fine-tune on HK plates | Pending |
| #6 | Ground truth + `benchmark.py` | Pending |
| #7 | GF17 camera investigation | ✅ Done — reposition recommended |
| #8 | Filter stationary/parked plates | Pending |

---

## Limitations

- **No ground truth** — cannot confirm if GF16 32→14 is over-dedup or correct
- **GF17 unusable** for benchmarking until camera repositioned
- **Single day of footage** — no night/rain/rush-hour coverage
