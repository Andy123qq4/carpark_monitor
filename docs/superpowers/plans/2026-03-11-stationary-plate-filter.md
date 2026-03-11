# Stationary Plate Filter Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse repeated detections of the same parked vehicle into a single dashboard row marked with a 🅿 badge, without touching the raw DB data.

**Architecture:** After `get_plate_sessions()` returns, a new `merge_stationary_sessions()` function in `db.py` groups same-plate sessions that share a similar bbox position and short time gap, merges them into the earliest session, and sets `is_stationary=True`. `app.py` calls this after the DB query. The template shows a badge for stationary rows.

**Tech Stack:** Python 3.11, SQLite (via sqlite3), FastAPI + Jinja2, pytest

---

## File Map

| File | Change |
|---|---|
| `db.py` | Add `merge_stationary_sessions()` + two private helpers `_centroid()`, `_dist()` |
| `app.py` | Call `merge_stationary_sessions()` in `index()` |
| `templates/index.html` | Add CSS for `.row-stationary` + 🅿 badge in plate cell |
| `tests/test_stationary.py` | New: unit tests for merge logic |

---

## Chunk 1: Core merge logic + tests

### Task 1: Write failing tests

**Files:**
- Create: `tests/test_stationary.py`

- [ ] **Step 1: Create tests file**

```python
# tests/test_stationary.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db


def _make_session(plate, ts, bbox_x, bbox_y, conf=0.9, video="GF18.mp4", frame=0):
    """Helper: build a session dict matching merge_stationary_sessions() input format."""
    det = {
        "video_file": video, "camera_id": "GF18", "frame_num": frame,
        "timestamp_sec": ts, "plate_text": plate, "confidence": conf,
        "bbox_x": bbox_x, "bbox_y": bbox_y, "bbox_w": 50, "bbox_h": 30,
    }
    return {"detection": det, "frame_count": 1, "is_stationary": False}


def test_no_sessions_returns_empty():
    assert db.merge_stationary_sessions([]) == []


def test_single_session_unchanged():
    sessions = [_make_session("WB6066", 100, 840, 800)]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["is_stationary"] is False


def test_two_sessions_same_spot_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("WB6066", 200, 842, 805),  # 14px apart, 100s gap
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["is_stationary"] is True
    assert result[0]["detection"]["timestamp_sec"] == 100  # earliest


def test_two_sessions_different_spot_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("WB6066", 200, 1400, 700),  # 560px apart
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2
    assert all(not s["is_stationary"] for s in result)


def test_two_sessions_too_far_apart_in_time_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("WB6066", 100 + 1801, 842, 805),  # >30 min gap
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2
    assert all(not s["is_stationary"] for s in result)


def test_different_plates_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("VH703",  200, 842, 805),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2
    assert all(not s["is_stationary"] for s in result)


def test_different_videos_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800, video="GF18.mp4"),
        _make_session("WB6066", 200, 842, 805, video="GF15.mp4"),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2


def test_merge_picks_highest_confidence_detection():
    sessions = [
        _make_session("WB6066", 100, 840, 800, conf=0.75),
        _make_session("WB6066", 200, 842, 805, conf=0.95),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["detection"]["confidence"] == 0.95


def test_merge_keeps_earliest_timestamp():
    sessions = [
        _make_session("WB6066", 200, 840, 800),
        _make_session("WB6066", 100, 842, 805),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["detection"]["timestamp_sec"] == 100


def test_frame_count_summed():
    s1 = _make_session("WB6066", 100, 840, 800)
    s2 = _make_session("WB6066", 200, 842, 805)
    s1["frame_count"] = 3
    s2["frame_count"] = 5
    result = db.merge_stationary_sessions([s1, s2])
    assert result[0]["frame_count"] == 8


def test_output_sorted_descending_by_timestamp():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("VH703",  300, 100, 100),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert result[0]["detection"]["timestamp_sec"] > result[1]["detection"]["timestamp_sec"]
```

- [ ] **Step 2: Run tests to confirm they all fail (function doesn't exist yet)**

```bash
cd /Users/tsugumi/Developer/carpark_monitor
python -m pytest tests/test_stationary.py -v 2>&1 | head -30
```

Expected: `AttributeError: module 'db' has no attribute 'merge_stationary_sessions'`

---

### Task 2: Implement merge_stationary_sessions in db.py

**Files:**
- Modify: `db.py` (append after `get_plate_sessions`)

- [ ] **Step 3: Add helpers and merge function to db.py**

Append to the end of `db.py`:

```python
import math


def _centroid(det: dict) -> tuple[float, float] | None:
    """Return bbox centroid (cx, cy) or None if no bbox."""
    if det.get("bbox_x") is None:
        return None
    return (det["bbox_x"] + det["bbox_w"] / 2, det["bbox_y"] + det["bbox_h"] / 2)


def _dist(a: tuple, b: tuple) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def merge_stationary_sessions(
    sessions: list[dict],
    max_gap_sec: float = 1800,
    max_dist_px: float = 300,
) -> list[dict]:
    """Merge same-plate sessions at similar bbox positions into one, marking is_stationary=True.

    Input: list of {"detection": dict|sqlite3.Row, "frame_count": int}
    Output: same structure with added "is_stationary": bool, merged rows removed.
    """
    if not sessions:
        return []

    # Normalise to plain dicts so we can mutate freely
    def _to_dict(s):
        det = s["detection"]
        if not isinstance(det, dict):
            det = {k: det[k] for k in det.keys()}
        return {"detection": det, "frame_count": s["frame_count"], "is_stationary": False}

    items = [_to_dict(s) for s in sessions]

    # Group indices by (video_file, plate_text)
    from collections import defaultdict
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, s in enumerate(items):
        key = (s["detection"]["video_file"], s["detection"]["plate_text"])
        groups[key].append(i)

    to_remove: set[int] = set()

    for indices in groups.values():
        if len(indices) < 2:
            continue
        # Sort ascending by timestamp for consecutive comparison
        indices.sort(key=lambda i: items[i]["detection"]["timestamp_sec"])

        # Greedy clustering: extend current cluster if within thresholds
        clusters: list[list[int]] = [[indices[0]]]
        for idx in indices[1:]:
            cur = items[idx]["detection"]
            last = items[clusters[-1][-1]]["detection"]
            gap = cur["timestamp_sec"] - last["timestamp_sec"]
            c1, c2 = _centroid(last), _centroid(cur)
            if gap <= max_gap_sec and c1 and c2 and _dist(c1, c2) <= max_dist_px:
                clusters[-1].append(idx)
            else:
                clusters.append([idx])

        for cluster in clusters:
            if len(cluster) < 2:
                continue
            # Pick best detection by confidence; keep earliest timestamp
            best_idx = max(cluster, key=lambda i: items[i]["detection"]["confidence"])
            earliest_idx = min(cluster, key=lambda i: items[i]["detection"]["timestamp_sec"])
            merged_det = {**items[best_idx]["detection"],
                          "timestamp_sec": items[earliest_idx]["detection"]["timestamp_sec"]}
            primary = cluster[0]  # index of first item (already earliest after sort)
            items[primary]["detection"] = merged_det
            items[primary]["is_stationary"] = True
            items[primary]["frame_count"] = sum(items[i]["frame_count"] for i in cluster)
            for i in cluster[1:]:
                to_remove.add(i)

    result = [s for i, s in enumerate(items) if i not in to_remove]
    return sorted(result, key=lambda s: s["detection"]["timestamp_sec"], reverse=True)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_stationary.py -v
```

Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_stationary.py
git commit -m "feat(db): add merge_stationary_sessions for parked vehicle dedup (#8)"
```

---

## Chunk 2: Wire into app + frontend badge

### Task 3: Call merge in app.py

**Files:**
- Modify: `app.py:54` — `index()` function

- [ ] **Step 6: Update index() to call merge**

In `app.py`, change the `index()` function body:

```python
@app.get("/", response_class=HTMLResponse)
def index(request: Request, video: str | None = None):
    detections = db.merge_stationary_sessions(db.get_plate_sessions(video_file=video))
    with db.get_conn() as conn:
        videos = [r["video_file"] for r in conn.execute(
            "SELECT DISTINCT video_file FROM detections ORDER BY video_file"
        ).fetchall()]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "detections": detections,
        "videos": videos,
        "selected_video": video,
    })
```

- [ ] **Step 7: Verify server starts without error**

```bash
uvicorn app:app --reload &
sleep 2
curl -s http://localhost:8000/ | grep -c "<tr"
# expect a number >= 1
kill %1
```

### Task 4: Add badge and styling to template

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 8: Add CSS for stationary rows**

Inside the `<style>` block (after the last existing rule), add:

```css
    .row-stationary { opacity: 0.65; }
    .badge-parked { font-size: 0.72rem; background: #e8f4e8; color: #2d7a2d; border: 1px solid #b2d8b2; border-radius: 3px; padding: 1px 5px; margin-left: 4px; vertical-align: middle; }
```

- [ ] **Step 9: Add is_stationary row class and badge**

Change the `<tr>` opening tag (line 89) from:

```html
      <tr data-timestamp="{{ d.timestamp_sec }}" data-confidence="{{ d.confidence }}">
```

to:

```html
      <tr data-timestamp="{{ d.timestamp_sec }}" data-confidence="{{ d.confidence }}"{% if s.is_stationary %} class="row-stationary"{% endif %}>
```

Change the plate cell (line 103-105) from:

```html
        <td>
          <strong>{{ d.plate_text }}</strong>
          <button class="play-btn" onclick="openClip('{{ d.video_file }}', {{ d.timestamp_sec }}, '{{ d.plate_text }}', {{ d.frame_num }})">▶</button>
          <button class="play-btn" onclick="launchViewer('{{ d.video_file }}', {{ d.timestamp_sec }})" title="Open in desktop viewer">👁</button>
        </td>
```

to:

```html
        <td>
          <strong>{{ d.plate_text }}</strong>{% if s.is_stationary %}<span class="badge-parked">🅿 停车</span>{% endif %}
          <button class="play-btn" onclick="openClip('{{ d.video_file }}', {{ d.timestamp_sec }}, '{{ d.plate_text }}', {{ d.frame_num }})">▶</button>
          <button class="play-btn" onclick="launchViewer('{{ d.video_file }}', {{ d.timestamp_sec }})" title="Open in desktop viewer">👁</button>
        </td>
```

- [ ] **Step 10: Manual check in browser**

```bash
uvicorn app:app --reload
# Open http://localhost:8000/?video=GF18+20260213+102947-104800.mp4
# Verify WB6066 shows as 1 row with 🅿 停车 badge and muted opacity
# Verify non-parked plates show as normal rows
```

- [ ] **Step 11: Commit**

```bash
git add app.py templates/index.html
git commit -m "feat(app/ui): show stationary badge for merged parked-vehicle sessions (#8)"
```

---

## Verification

- [ ] GF18: WB6066 appears as exactly **1 row** (was 5), marked 🅿 停车
- [ ] GF15/GF16: all other plates unaffected
- [ ] Frame count on the stationary row reflects the summed count from merged sessions
- [ ] All 11 pytest tests pass: `python -m pytest tests/test_stationary.py -v`
