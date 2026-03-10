# INPUT: SQLite DB (data/carpark.db), video files in video/
# OUTPUT: HTTP endpoints for web dashboard + frame extraction
# ROLE: API controller — serve detection results and frame snapshots via web UI

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import cv2
import db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def fmt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

templates.env.filters["timestamp"] = fmt_timestamp

db.init_db()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, video: str = None):
    detections = db.get_detections(video_file=video)
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

@app.get("/frame/{video_file}/{frame_num}")
def get_frame(video_file: str, frame_num: int):
    cap = cv2.VideoCapture(f"video/{video_file}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    cap.release()
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return Response(content=buffer.tobytes(), media_type="image/jpeg")
