# INPUT: path to video file (CLI arg)
# OUTPUT: plate detections written to SQLite DB
# ROLE: core pipeline — extract frames, run ALPR, validate, persist

import argparse
import os
import time
from pathlib import Path

import cv2
from dotenv import load_dotenv

import db
import dedup

load_dotenv()  # must run before importing detection (reads PLATE_RECOGNIZER_API at module level)
os.environ["ONNXRUNTIME_LOG_SEVERITY_LEVEL"] = "4"  # suppress CoreML errors
import detection  # noqa: E402

DETECTION_DIR = Path("data/detections")

def extract_crop(frame, bbox, wide: bool = False):
    """Extract plate region from frame. Wide mode adds 100px context for API."""
    if not bbox:
        return None
    x, y, w, h = bbox
    fh, fw = frame.shape[:2]
    pad = 100 if wide else 4
    crop = frame[max(0, y - pad):min(fh, y + h + pad), max(0, x - pad):min(fw, x + w + pad)]
    return crop if crop.size > 0 else None


def save_crop(crop, camera_id, frame_num, text):
    if crop is None:
        return None
    DETECTION_DIR.mkdir(parents=True, exist_ok=True)
    crop_path = DETECTION_DIR / f"{camera_id}_{frame_num}_{text}_crop.jpg"
    cv2.imwrite(str(crop_path), crop)
    return crop_path


def process_video(video_path: str, backend: str = "fast_alpr"):
    db.init_db()
    camera_id = detection.parse_camera_id(video_path)
    video_file = Path(video_path).name

    if backend == "plate_recognizer":
        detector = detection.PlateRecognizerDetector(frame_interval=150)
    elif backend == "hybrid":
        if not detection.PLATE_RECOGNIZER_TOKEN:
            print("ERROR: PLATE_RECOGNIZER_API env var not set (check .env file)")
            return
        detector = detection.ALPRDetector(use_coreml=True)
    else:
        detector = detection.ALPRDetector(use_coreml=True)
    tracker = dedup.TemporalTracker(pick_best_crop=(backend == "hybrid"))
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_num = 0
    detected = 0

    print(f"Processing {video_file} (camera: {camera_id}, fps: {fps:.1f})")

    def emit(emissions):
        nonlocal detected
        for text, conf, bbox, crop, best_frame, best_ts in emissions:
            source = "local"
            if backend == "hybrid" and crop is not None:
                api_result = detection.recognize_crop(crop)
                if api_result:
                    text, conf = api_result
                    source = "API"
                    time.sleep(1.0)  # rate limit
            db.save_detection(video_file, camera_id, best_frame, best_ts, text, conf, bbox)
            img_path = save_crop(crop, camera_id, best_frame, text)
            detected += 1
            bbox_msg = f" bbox={bbox}" if bbox else " [no bbox]"
            print(f"  [{best_ts:.1f}s] {text} ({conf:.2f}){bbox_msg} [{source}] -> {img_path}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_num % detector.frame_interval == 0:
            timestamp_sec = frame_num / fps
            raw = detector.detect_frame(frame)
            wide = (backend == "hybrid")
            detections = [(text, conf, bbox, extract_crop(frame, bbox, wide=wide)) for text, conf, bbox in raw]
            emit(tracker.update(detections, frame_num, timestamp_sec))
            if backend == "plate_recognizer":
                time.sleep(1.0)

        frame_num += 1

    emit(tracker.flush())
    cap.release()
    print(f"Done. {frame_num} frames scanned, {detected} plates saved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--backend", choices=["fast_alpr", "plate_recognizer", "hybrid"], default="fast_alpr")
    args = parser.parse_args()
    process_video(args.video, backend=args.backend)
