# Carpark Monitor MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process a single .avi CCTV file, detect HK car plates with fast-alpr, store results in SQLite, and display them in a FastAPI web dashboard.

**Architecture:** cv2 extracts every Nth frame → fast-alpr detects plate bounding box then OCRs text → HK regex validates result → saved to SQLite → FastAPI serves plain HTML table.

**Tech Stack:** Python, fast-alpr, opencv-python, FastAPI, Jinja2, SQLite (stdlib), uvicorn

---

## Chunk 1: Setup

### Task 1: Requirements + DB module

**Files:**
- Create: `requirements.txt`
- Create: `db.py`

- [ ] **Step 1: Create requirements.txt**

```
fast-alpr[onnx]
opencv-python
fastapi
uvicorn[standard]
jinja2
```

- [ ] **Step 2: Install deps**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error. `fast-alpr[onnx]` installs onnxruntime (required — without it ALPR() will crash). Models download on first use (~30MB).

- [ ] **Step 3: Create db.py**

```python
# INPUT: none (creates DB file on import)
# OUTPUT: init_db(), save_detection(), get_detections()
# ROLE: data access layer — SQLite read/write for plate detections

import sqlite3
from pathlib import Path

DB_PATH = Path("data/carpark.db")

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                video_file    TEXT NOT NULL,
                camera_id     TEXT NOT NULL,
                frame_num     INTEGER NOT NULL,
                timestamp_sec REAL NOT NULL,
                plate_text    TEXT NOT NULL,
                confidence    REAL NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)

def save_detection(video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO detections (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence) VALUES (?,?,?,?,?,?)",
            (video_file, camera_id, frame_num, timestamp_sec, plate_text, confidence)
        )

def get_detections(video_file=None):
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        if video_file:
            return conn.execute(
                "SELECT * FROM detections WHERE video_file=? ORDER BY timestamp_sec", (video_file,)
            ).fetchall()
        return conn.execute("SELECT * FROM detections ORDER BY created_at DESC, timestamp_sec").fetchall()
```

- [ ] **Step 4: Smoke test db.py**

```bash
python -c "
import db, sqlite3
db.init_db()
db.save_detection('test.avi', 'GF15', 1, 0.5, 'AB 1234', 0.95)
rows = db.get_detections('test.avi')
assert len(rows) == 1
assert rows[0]['plate_text'] == 'AB 1234'
# cleanup test row
with db.get_conn() as conn:
    conn.execute(\"DELETE FROM detections WHERE video_file='test.avi'\")
print('db OK')
"
```

Expected: `db OK`

- [ ] **Step 5: Create .gitignore and commit**

```bash
cat > .gitignore << 'EOF'
data/carpark.db
video/*.avi
__pycache__/
*.pyc
.superpowers/
EOF
mkdir -p data && touch data/.gitkeep
git add requirements.txt db.py .gitignore data/.gitkeep
git commit -m "feat: add db module, requirements, and gitignore"
```

---

## Chunk 2: Processor

### Task 2: processor.py — video → plate detections → DB

**Files:**
- Create: `processor.py`

- [ ] **Step 1: Create processor.py**

```python
# INPUT: path to .avi file (CLI arg)
# OUTPUT: plate detections written to SQLite DB
# ROLE: core pipeline — extract frames, run ALPR, validate, persist

import re
import sys
from pathlib import Path

import cv2
from fast_alpr import ALPR

import db

# HK plate: 1-2 letters, optional space, 1-4 digits
HK_PLATE_RE = re.compile(r'^[A-Z]{1,2}\s?[0-9]{1,4}$')
FRAME_INTERVAL = 10      # process every 10th frame (~3 fps for 30fps video)
MIN_CONFIDENCE = 0.5

def parse_camera_id(video_path: str) -> str:
    """Extract camera ID from filename, e.g. 'GF15 ...' -> 'GF15'"""
    name = Path(video_path).stem
    return name.split()[0] if ' ' in name else name

def process_video(video_path: str):
    db.init_db()
    camera_id = parse_camera_id(video_path)
    video_file = Path(video_path).name

    alpr = ALPR()
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_num = 0
    detected = 0

    print(f"Processing {video_file} (camera: {camera_id}, fps: {fps:.1f})")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_num % FRAME_INTERVAL == 0:
            results = alpr.predict(frame)
            for result in results:
                if result.ocr is None:
                    continue
                text = result.ocr.text.upper().strip()
                conf = result.ocr.confidence
                # confidence can be list[float] (per-character) — average it
                if isinstance(conf, list):
                    conf = sum(conf) / len(conf) if conf else 0.0

                if conf < MIN_CONFIDENCE:
                    continue
                if not HK_PLATE_RE.match(text):
                    continue

                timestamp_sec = frame_num / fps
                db.save_detection(video_file, camera_id, frame_num, timestamp_sec, text, conf)
                detected += 1
                print(f"  [{timestamp_sec:.1f}s] {text} ({conf:.2f})")

        frame_num += 1

    cap.release()
    print(f"Done. {frame_num} frames scanned, {detected} plates saved.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python processor.py <path/to/video.avi>")
        sys.exit(1)
    process_video(sys.argv[1])
```

- [ ] **Step 2: Run on first video — smoke test**

```bash
python processor.py "video/GF15 20260212 142142-145519.avi"
```

Expected: progress output showing frames scanned and any plates found. First run will download ONNX models (~30MB).

- [ ] **Step 3: Verify detections saved**

```bash
python -c "
import db
rows = db.get_detections()
print(f'{len(rows)} detections total')
for r in rows[:5]:
    print(dict(r))
"
```

- [ ] **Step 4: Commit**

```bash
git add processor.py
git commit -m "feat: add video processor with fast-alpr and HK plate validation"
```

---

## Chunk 3: Web Dashboard

### Task 3: FastAPI app + HTML template

**Files:**
- Create: `app.py`
- Create: `templates/index.html`

- [ ] **Step 1: Create app.py**

```python
# INPUT: SQLite DB (data/carpark.db)
# OUTPUT: HTTP endpoints for web dashboard
# ROLE: API controller — serve detection results via web UI

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

db.init_db()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, video: str = None):
    detections = db.get_detections(video_file=video)
    # Get distinct video files for the dropdown
    import sqlite3
    with db.get_conn() as conn:
        conn.row_factory = sqlite3.Row
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

- [ ] **Step 2: Create templates/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Carpark Monitor</title>
  <style>
    body { font-family: sans-serif; padding: 2rem; max-width: 900px; margin: 0 auto; }
    h1 { font-size: 1.4rem; }
    select, button { padding: 0.4rem 0.8rem; margin-right: 0.5rem; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd; }
    th { background: #f5f5f5; }
    .confidence { color: #888; }
  </style>
</head>
<body>
  <h1>Carpark Monitor — Plate Detections</h1>

  <form method="get">
    <select name="video">
      <option value="">All videos</option>
      {% for v in videos %}
        <option value="{{ v }}" {% if v == selected_video %}selected{% endif %}>{{ v }}</option>
      {% endfor %}
    </select>
    <button type="submit">Filter</button>
  </form>

  <table>
    <thead>
      <tr>
        <th>Video</th>
        <th>Camera</th>
        <th>Time (s)</th>
        <th>Frame</th>
        <th>Plate</th>
        <th>Confidence</th>
      </tr>
    </thead>
    <tbody>
      {% for d in detections %}
      <tr>
        <td>{{ d.video_file }}</td>
        <td>{{ d.camera_id }}</td>
        <td>{{ "%.1f"|format(d.timestamp_sec) }}</td>
        <td>{{ d.frame_num }}</td>
        <td><strong>{{ d.plate_text }}</strong></td>
        <td class="confidence">{{ "%.0f"|format(d.confidence * 100) }}%</td>
      </tr>
      {% else %}
      <tr><td colspan="6" style="color:#999">No detections yet. Run processor.py first.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
```

- [ ] **Step 3: Start server and verify**

```bash
uvicorn app:app --reload
```

Open http://localhost:8000 — should show the table with detections from step 2.

- [ ] **Step 4: Commit**

```bash
git add app.py templates/index.html
git commit -m "feat: add FastAPI dashboard with plate detection table"
```

---

## Chunk 4: Run All Videos

### Task 4: Process remaining 3 videos and verify

- [ ] **Step 1: Process all videos**

```bash
python processor.py "video/GF16 20260213 102959-104800.avi"
python processor.py "video/GF17 20260212 142152-145500.avi"
python processor.py "video/GF18 20260213 102947-104800.avi"
```

- [ ] **Step 2: Check totals**

```bash
python -c "
import db
rows = db.get_detections()
from collections import Counter
by_cam = Counter(r['camera_id'] for r in rows)
print(f'Total detections: {len(rows)}')
for cam, n in sorted(by_cam.items()):
    print(f'  {cam}: {n}')
"
```

- [ ] **Step 3: Review dashboard**

Open http://localhost:8000 — verify all 4 cameras appear in dropdown, plates look plausible.

- [ ] **Step 4: Commit (nothing to stage — no source files change in this chunk)**

```bash
git status  # confirm nothing new to commit
```

---

## Notes / Known Limitations (post-MVP)

- No deduplication yet — same plate across 2 entry cameras will appear twice
- No entry/exit logic — just raw detections per video
- `fast-alpr` OCR can struggle with blurry/dark frames; tune `MIN_CONFIDENCE` threshold
- HK plate regex may need updating for special plates (e.g. `王 0001` diplomatic, `XX 0000` gov)
