# INPUT: SQLite DB (data/carpark.db), annotated JPGs in data/detections/, video files in video/
# OUTPUT: HTTP dashboard with plate detection table, MJPEG clip viewer, SSE realtime stream
# ROLE: API controller — serve detection results, video clips, and realtime processing

import asyncio
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db
import dedup
import detection

app = FastAPI()
Path("data/detections").mkdir(parents=True, exist_ok=True)
app.mount("/detections", StaticFiles(directory="data/detections"), name="detections")
templates = Jinja2Templates(directory="templates")

_executor = ThreadPoolExecutor(max_workers=4)
_VIDEO_DIR = Path("video").resolve()


def _safe_video_path(filename: str) -> Path:
    """Resolve path and verify it stays within the video/ directory."""
    path = (_VIDEO_DIR / filename).resolve()
    if not path.is_relative_to(_VIDEO_DIR) or not path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")
    return path


def fmt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

templates.env.filters["timestamp"] = fmt_timestamp

db.init_db()


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


GT_PATH = Path("data/ground_truth.json")


@app.get("/annotate", response_class=HTMLResponse)
def annotate(request: Request, video: str | None = None):
    with db.get_conn() as conn:
        videos = [r["video_file"] for r in conn.execute(
            "SELECT DISTINCT video_file FROM detections ORDER BY video_file"
        ).fetchall()]
    events = db.get_annotation_events(video) if video else []
    gt = json.loads(GT_PATH.read_text()) if GT_PATH.exists() else {}
    return templates.TemplateResponse("annotate.html", {
        "request": request,
        "videos": videos,
        "selected_video": video,
        "events": events,
        "gt": gt,
    })


@app.post("/api/annotate/save")
async def save_annotation(request: Request):
    body = await request.json()
    gt = json.loads(GT_PATH.read_text()) if GT_PATH.exists() else {}
    video = body["video_file"]
    if video not in gt:
        gt[video] = {}
    gt[video][str(body["event_id"])] = {
        "plate_text": body["plate_text"].strip().upper(),
        "start_ts": body["start_ts"],
        "end_ts": body["end_ts"],
        "note": body.get("note", ""),
    }
    GT_PATH.parent.mkdir(exist_ok=True)
    GT_PATH.write_text(json.dumps(gt, indent=2, ensure_ascii=False))
    return {"ok": True, "saved": len(gt[video])}


@app.get("/benchmark", response_class=HTMLResponse)
def benchmark(request: Request, video: str | None = None):
    gt_all = json.loads(GT_PATH.read_text()) if GT_PATH.exists() else {}
    with db.get_conn() as conn:
        videos = [r["video_file"] for r in conn.execute(
            "SELECT DISTINCT video_file FROM detections ORDER BY video_file"
        ).fetchall()]

    results = {}
    for vid in (([video] if video else videos)):
        gt_vid = gt_all.get(vid, {})
        if not gt_vid:
            continue
        pipeline = db.merge_stationary_sessions(db.get_plate_sessions(video_file=vid))
        detected = {s["detection"]["plate_text"] for s in pipeline}
        gt_plates = set()
        for v in gt_vid.values():
            for p in v["plate_text"].split("+"):
                p = p.strip()
                if p:
                    gt_plates.add(p)

        tp = detected & gt_plates
        fp = detected - gt_plates
        fn = gt_plates - detected
        precision = len(tp) / len(detected) if detected else 0.0
        recall = len(tp) / len(gt_plates) if gt_plates else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        results[vid] = {
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "gt_count": len(gt_plates),
            "detected_count": len(detected),
        }

    return templates.TemplateResponse("benchmark.html", {
        "request": request,
        "videos": videos,
        "selected_video": video,
        "results": results,
        "gt_exists": GT_PATH.exists(),
    })


@app.post("/api/viewer")
def launch_viewer(video: str, ts: float = 0.0):
    """Launch the OpenCV viewer as a local subprocess, 2s before detection for 10s."""
    video_path = _safe_video_path(video)
    start = max(0.0, ts - 2.0)
    subprocess.Popen(
        [sys.executable, "viewer.py", str(video_path),
         "--start", str(start), "--duration", "10"],
        cwd=str(Path.cwd()),
    )
    return {"status": "launched", "video": video, "start": round(start, 1)}


def _interpolate_bbox(keyframes: list[dict], cur_frame: int):
    """Linearly interpolate bbox between detection keyframes.
    Returns (x, y, w, h, plate_text, confidence) or None."""
    if not keyframes:
        return None
    # Before first or after last keyframe — use nearest within a small margin
    first, last = keyframes[0], keyframes[-1]
    margin = 10  # extra frames to hold the bbox visible beyond keyframes
    if cur_frame < first["frame_num"] - margin or cur_frame > last["frame_num"] + margin:
        return None
    if cur_frame <= first["frame_num"]:
        k = first
        return k["bbox_x"], k["bbox_y"], k["bbox_w"], k["bbox_h"], k["plate_text"], k["confidence"]
    if cur_frame >= last["frame_num"]:
        k = last
        return k["bbox_x"], k["bbox_y"], k["bbox_w"], k["bbox_h"], k["plate_text"], k["confidence"]
    # Find surrounding keyframes
    for i in range(len(keyframes) - 1):
        a, b = keyframes[i], keyframes[i + 1]
        if a["frame_num"] <= cur_frame <= b["frame_num"]:
            span = b["frame_num"] - a["frame_num"]
            t = (cur_frame - a["frame_num"]) / span if span else 0
            x = int(a["bbox_x"] + t * (b["bbox_x"] - a["bbox_x"]))
            y = int(a["bbox_y"] + t * (b["bbox_y"] - a["bbox_y"]))
            w = int(a["bbox_w"] + t * (b["bbox_w"] - a["bbox_w"]))
            h = int(a["bbox_h"] + t * (b["bbox_h"] - a["bbox_h"]))
            conf = a["confidence"] if a["confidence"] >= b["confidence"] else b["confidence"]
            return x, y, w, h, a["plate_text"], conf
    return None


@app.get("/api/clip/{filename:path}")
async def serve_clip(filename: str, ts: float = 0.0, plate: str = "", frame_num: int = -1):
    """MJPEG stream: 7s clip starting 2s before the detection timestamp."""
    video_path = _safe_video_path(filename)

    # Load ALL detections in the clip's frame range for continuous overlay
    detection_keyframes: dict[str, list[dict]] = {}  # plate_text -> sorted keyframes
    with db.get_conn() as conn:
        fps_est = 30.0  # rough estimate for query range; exact fps used in reader
        start_f = max(0, int((ts - 2.0) * fps_est))
        end_f = int((ts + 5.0) * fps_est)
        rows = conn.execute(
            "SELECT frame_num, plate_text, confidence, bbox_x, bbox_y, bbox_w, bbox_h "
            "FROM detections WHERE video_file=? AND bbox_x IS NOT NULL "
            "AND frame_num BETWEEN ? AND ? ORDER BY frame_num",
            (filename, start_f - 30, end_f + 30),
        ).fetchall()
        for r in rows:
            detection_keyframes.setdefault(r["plate_text"], []).append(dict(r))

    async def generate():
        queue: asyncio.Queue = asyncio.Queue(maxsize=60)
        loop = asyncio.get_event_loop()
        cancel = threading.Event()

        def read_frames():
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

            start_frame = max(0, int((ts - 2.0) * fps))
            end_frame = int((ts + 5.0) * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            while not cancel.is_set():
                cur_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if cur_frame > end_frame:
                    break
                ret, frame = cap.read()
                if not ret:
                    break

                # Draw interpolated bboxes for all detected plates in range
                for plate_text, keyframes in detection_keyframes.items():
                    result = _interpolate_bbox(keyframes, cur_frame)
                    if result is None:
                        continue
                    x, y, w, h, _, conf = result
                    detection.draw_bbox_label(frame, (x, y, w, h), f"{plate_text} ({conf*100:.0f}%)")

                # Timestamp overlay
                ts_text = fmt_timestamp(cur_frame / fps)
                cv2.putText(frame, ts_text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
                cv2.putText(frame, ts_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                asyncio.run_coroutine_threadsafe(queue.put(buf.tobytes()), loop)
                cancel.wait(timeout=1.0 / fps)

            cap.release()
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(_executor, read_frames)

        try:
            while True:
                data = await queue.get()
                if data is None:
                    break
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + data + b'\r\n'
        finally:
            cancel.set()

    return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')


@app.get("/api/realtime")
async def realtime_stream(video: str, request: Request):
    """SSE endpoint: process video at real speed, stream detections as events."""
    video_path = _safe_video_path(video)

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        cancel = threading.Event()

        def process():
            camera_id = detection.parse_camera_id(video)
            detector = detection.ALPRDetector(use_coreml=True)
            tracker = dedup.TemporalTracker()
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_num = 0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            while not cancel.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_num % detector.frame_interval == 0:
                    timestamp_sec = frame_num / fps
                    raw = detector.detect_frame(frame)
                    for text, conf, bbox in tracker.update(raw, frame_num, timestamp_sec):
                        event_data = {
                            "plate": text,
                            "confidence": round(conf, 4),
                            "timestamp_sec": round(timestamp_sec, 2),
                            "frame_num": frame_num,
                            "camera_id": camera_id,
                            "video_file": video,
                            "progress": round(frame_num / total_frames * 100, 1) if total_frames else 0,
                        }
                        asyncio.run_coroutine_threadsafe(queue.put(event_data), loop)

                frame_num += 1
                cancel.wait(timeout=1.0 / fps)

            cap.release()
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(_executor, process)

        yield "data: {\"status\": \"started\"}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=2.0)
                    if data is None:
                        yield "data: {\"status\": \"done\"}\n\n"
                        break
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            cancel.set()

    return StreamingResponse(event_stream(), media_type='text/event-stream',
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
