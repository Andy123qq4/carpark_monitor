# Stationary Plate Filter — Design Spec

> Date: 2026-03-11
> Task: #8

## Problem

Parked vehicles generate multiple detection rows in the dashboard. GF18's WB6066 produces 5 rows over ~4 minutes despite never moving — the `TemporalTracker`'s 30-frame cluster window expires repeatedly, each expiry emitting a new "visit" to the DB. The raw data is correct; the display is misleading.

## Goal

Collapse repeated detections of the same stationary vehicle into **1 row** in the dashboard, labelled with a "🅿 停车" badge. Raw DB rows are untouched.

## Approach: Display-layer Python merge

After `get_plate_sessions()` returns, a new `merge_stationary_sessions()` helper merges sessions that match all three criteria:

| Criterion | Threshold | Rationale |
|---|---|---|
| Same plate text + same video file | exact match | Different cameras are independent |
| Bbox centroid distance | ≤ 300px | Same parking spot; accounts for OCR bbox noise |
| Time gap between consecutive sessions | ≤ 1800s (30 min) | Allows brief occlusion; rules out genuine re-entry |

When sessions are merged, the output row keeps:
- `first_seen` from the earliest session
- `last_seen` from the latest session
- `confidence` from the highest-confidence individual detection
- `crop_path` from the highest-confidence detection
- `is_stationary = True`

## Files Changed

| File | Change |
|---|---|
| `db.py` | Add `merge_stationary_sessions(sessions)` function |
| `app.py` | Call `merge_stationary_sessions()` in `index()` after `get_plate_sessions()` |
| `templates/index.html` | Show 🅿 badge and muted row style for `is_stationary` sessions |

## Non-Goals

- No DB schema changes
- No changes to `processor.py` or `dedup.py`
- No hiding of stationary plates — they remain visible, just merged

## Stationary Detection Logic

```python
def _bbox_centroid(session) -> tuple[float, float] | None:
    if session.get("bbox_x") is None:
        return None
    return (session["bbox_x"] + session["bbox_w"] / 2,
            session["bbox_y"] + session["bbox_h"] / 2)

def _centroid_dist(a, b) -> float:
    ax, ay = a
    bx, by = b
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

def merge_stationary_sessions(sessions, max_gap_sec=1800, max_dist_px=300):
    # Group by (video_file, plate_text), sort by first_seen
    # For each group, greedily merge consecutive sessions within thresholds
    # Mark merged groups is_stationary=True
    ...
```

## Thresholds

Both thresholds are parameters with defaults. Tuning guide:
- Reduce `max_dist_px` if unrelated plates in same region are wrongly merged
- Reduce `max_gap_sec` if legitimate re-entries of the same plate within 30 min should show separately
