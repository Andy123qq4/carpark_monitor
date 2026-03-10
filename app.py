# INPUT: SQLite DB (data/carpark.db)
# OUTPUT: HTTP endpoints for web dashboard
# ROLE: API controller — serve detection results via web UI

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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
