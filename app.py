# INPUT: SQLite DB (data/carpark.db), annotated JPGs in data/detections/
# OUTPUT: HTTP dashboard with plate detection table and images
# ROLE: API controller — serve detection results and saved annotated frames

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import db

app = FastAPI()
Path("data/detections").mkdir(parents=True, exist_ok=True)
app.mount("/detections", StaticFiles(directory="data/detections"), name="detections")
templates = Jinja2Templates(directory="templates")

def fmt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

templates.env.filters["timestamp"] = fmt_timestamp

db.init_db()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, video: str | None = None):
    detections = db.get_plate_sessions(video_file=video)
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

