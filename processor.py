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
