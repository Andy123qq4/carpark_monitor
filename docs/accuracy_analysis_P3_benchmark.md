# Accuracy Analysis — GF15 Ground Truth Benchmark (Post-P3 CLAHE)

> Last updated: 2026-03-11
> GF15 only (29 events manually annotated).

---

## Benchmark Setup

- **Video**: GF15 20260212 142142-145519.avi (33.5 min)
- **GT collection method**: `/annotate` UI — per-event manual labelling, multi-car events written as `PLATE1 + PLATE2`
- **GT events**: 29 events → 29 unique GT plates
- **Matching**: fuzzy — `plates_similar()` used for TP/FP classification (tolerates OCR variants within confusion map)

---

## Results Comparison

| Metric | Baseline (P2) | Post-P3 (CLAHE) | Delta |
|---|---|---|---|
| **Precision** | 24% (23/97) | **26% (19/73)** | +2% |
| **Recall** | 79% (23/29) | **66% (19/29)** | **-13%** |
| **F1** | 37% | **37%** | 0 |
| Sessions | 97 | 73 | -24 |
| TP | 23 | 19 | -4 |
| FP | 73 | 48 | -25 |
| FN | 6 | 10 | +4 |

---

## P3 Assessment: Neutral / Slightly Negative

CLAHE preprocessing **reduced session count by 25%** (97→73), which is good — the OCR is producing fewer noisy reads. However, **Recall dropped from 79% to 66%**, meaning CLAHE caused 4 previously-detected vehicles to be missed.

### Why Recall dropped

CLAHE sharpened some crops but over-enhanced others, changing the OCR output in ways that broke prior correct reads:

| FN added by P3 | Was detected as (pre-P3) | Post-P3 read |
|---|---|---|
| `MK982` | `MK982` ✓ direct | OCR now reads differently, fails HK regex |
| `NN3303` | `NN3303` ✓ | |
| `TA517` | `TA517` ✓ | |
| `WW7303` | `WW7303` ✓ | |

### Fuzzy TP (P3 introduced minor variants that still match)

6 GT plates were detected with slight OCR drift but still matched via `plates_similar()`:
`SV9500→SY9500`, `TJ155→TJ1551`, `UG7168→UG7169`, `JX307→JX3032`, `ME879→ME8791`, `XN586→XN5586`

### Why Precision barely improved (+2%)

The root FP cause (digit substitutions `3↔9`, `4↔9`, `I↔Z`) is **not correctable by local contrast enhancement**. These errors occur because:
- The ONNX OCR model was not trained on HK plates
- Certain digit shapes are genuinely ambiguous at low resolution regardless of contrast

---

## Root Cause (unchanged from baseline)

> **The bottleneck is OCR model accuracy, not image contrast.**

P3 (CLAHE) is the wrong lever. The correct fixes:
1. **P4**: Plate Recognizer API — commercial model trained on real plates globally
2. **P5**: Fine-tune ONNX model on HK plate dataset

---

## Updated Roadmap

| Task | Fix | Status |
|---|---|---|
| P1 | Multi-frame confidence voting | ✅ Done |
| P2 | Expanded confusion map + length tolerance + normalize_plate | ✅ Done |
| P2b | V↔Y↔W, B↔D↔G confusions | ✅ Done |
| #6 | Ground truth + annotation UI + benchmark page | ✅ Done (GF15 annotated) |
| #7 | GF17 camera investigation | ✅ Done — reposition recommended |
| #8 | Filter stationary/parked plates | ✅ Done |
| P3 | CLAHE preprocessing on crops | ✅ Done — neutral result, Recall -13% offset gains |
| **P4** | **Plate Recognizer API trial** | **Next recommended** |
| P5 | Fine-tune ONNX model on HK plates | Pending |

