# Accuracy Analysis — GF15 Ground Truth Benchmark (Post-#6)

> Last updated: 2026-03-11
> First benchmark with real ground truth. GF15 only (29 events manually annotated).
> Pipeline: P1 + P2 + P2b + #8 (stationary filter).

---

## Benchmark Setup

- **Video**: GF15 20260212 142142-145519.mp4 (33.5 min)
- **GT collection method**: `/annotate` UI — per-event manual labelling, multi-car events written as `PLATE1 + PLATE2`
- **GT events**: 29 events → 30 unique GT plates (one event had 2 cars simultaneously)
- **Pipeline output**: `merge_stationary_sessions(get_plate_sessions())` → 96 sessions
- **Matching**: fuzzy — `plates_similar()` used for TP/FP classification (tolerates OCR variants within confusion map)

---

## GF15 Results

| Metric | Value |
|---|---|
| **Precision** | **24%** (23 / 96 sessions match a GT plate) |
| **Recall** | **79%** (23 / 29 GT vehicles detected) |
| **F1** | **37%** |
| GT vehicles | 29 |
| Pipeline sessions | 96 |
| TP | 23 |
| FP | 73 |
| FN | 6 |

---

## Root Cause Analysis

### Why Precision is 24%

The 73 FP sessions are **not random noise** — they are OCR variant reads of real vehicles that `dedup` failed to merge:

**Example: `ZL9679` (real plate)**
- Pipeline output: `ZL9679` ✓, `ZL3679`, `ZL4679`, `ZI9679`, `IL9679` — 5 sessions for 1 car
- 4 variants become FP because `3↔9`, `4↔9`, `I↔Z` are not in the confusion map (and shouldn't be — they are OCR errors, not visually similar characters)
- **Root cause**: OCR is reading `9` as `3` or `4`, `Z` as `I` — these are image quality / contrast issues

**Pattern across all FP:**
- Digit substitutions: `3↔9`, `4↔9`, `7↔1`, `6↔0` (OCR ambiguity on low-contrast crops)
- Letter substitutions: `I↔Z`, `K↔X`, `L↔T`, `V↔A` (thin stroke confusion)
- These are not fixable by expanding the confusion map — the characters are not visually similar, they are **misread due to poor image quality**

### Why Recall is 79% (6 FN)

| Missed plate | Likely reason |
|---|---|
| `PD6719` | Only appeared as `PD6795`/`PD6715` — no OCR read close enough to match |
| `TW2568` | Only appeared as `TM2266`/`TW2259` — both differ by 2+ chars |
| `UK9553` | Only appeared as `UX9893`/`VB9553` — high OCR error rate |
| `WV5597` | Only appeared as `HV5597`/`HX5577`/`MY557` — W→H confusion not in map |
| `YL4388` | Only appeared as `XL4358` — Y→X not in map |
| `YN7791` | Only appeared as `YH77` (truncated) — bbox too small/blurry |

All 6 FN are cases where the **crop image quality was too poor** for the OCR to read the plate within the confusion map's tolerance.

---

## Key Insight

> **The bottleneck is OCR accuracy on low-quality crops, not the confusion map.**

Expanding the confusion map further would increase recall marginally but destroy precision (over-merging unrelated plates). The correct fix is **better input images to the OCR** — which is P3.

---

## Roadmap Status Update

| Task | Fix | Status |
|---|---|---|
| P1 | Multi-frame confidence voting | ✅ Done |
| P2 | Expanded confusion map + length tolerance + normalize_plate | ✅ Done |
| P2b | Add V↔Y↔W, B↔D↔G confusions | ✅ Done |
| #6 | Ground truth + annotation UI + benchmark page | ✅ Done (GF15 annotated) |
| #7 | GF17 camera investigation | ✅ Done — reposition recommended |
| #8 | Filter stationary/parked plates | ✅ Done |
| **P3** | **CLAHE preprocessing on crops** | **Next — highest ROI** |
| P4 | Plate Recognizer API trial | Pending (low priority) |
| P5 | Fine-tune on HK plates | Pending (low priority) |

---

## Expected Impact of P3 (CLAHE)

CLAHE (Contrast Limited Adaptive Histogram Equalization) applied to plate crops before OCR should:

1. **Improve digit disambiguation** — `3/9`, `4/9`, `6/0` variants reduced → fewer FP sessions per vehicle
2. **Improve letter disambiguation** — `I/Z`, `K/X` reduced → better Recall
3. **Expected Precision improvement**: 24% → 50%+ (rough estimate — if avg sessions per vehicle drops from 3→1.5)
4. **Expected Recall improvement**: 79% → 85%+ (FN cases are mostly blurry crops)

Benchmark re-run after P3 will confirm.
