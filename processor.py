# INPUT: path to .avi file (CLI arg)
# OUTPUT: plate detections written to SQLite DB
# ROLE: core pipeline — extract frames, run ALPR, validate, persist

import os
import sys
from pathlib import Path

os.environ["ONNXRUNTIME_LOG_SEVERITY_LEVEL"] = "3"  # suppress CoreML fallback noise

import cv2

import db
import dedup
import detection

DETECTION_DIR = Path("data/detections")

def save_annotated_frame(frame, bbox, text, conf, camera_id, frame_num):
    if not bbox:
        return None
    DETECTION_DIR.mkdir(parents=True, exist_ok=True)
    x, y, w, h = bbox
    pad = 4
    crop = frame[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    if crop.size == 0:
        return None
    crop_path = DETECTION_DIR / f"{camera_id}_{frame_num}_{text}_crop.jpg"
    cv2.imwrite(str(crop_path), crop)
    return crop_path


def process_video(video_path: str):
    db.init_db()
    camera_id = detection.parse_camera_id(video_path)
    video_file = Path(video_path).name

    detector = detection.ALPRDetector(use_coreml=True)
    tracker = dedup.TemporalTracker()
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_num = 0
    detected = 0

    print(f"Processing {video_file} (camera: {camera_id}, fps: {fps:.1f})")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_num % detector.frame_interval == 0:
            timestamp_sec = frame_num / fps
            raw = detector.detect_frame(frame)
            for text, conf, bbox in tracker.update(raw, frame_num, timestamp_sec):
                db.save_detection(video_file, camera_id, frame_num, timestamp_sec, text, conf, bbox)
                img_path = save_annotated_frame(frame, bbox, text, conf, camera_id, frame_num)
                detected += 1
                bbox_msg = f" bbox={bbox}" if bbox else " [no bbox]"
                print(f"  [{timestamp_sec:.1f}s] {text} ({conf:.2f}){bbox_msg} -> {img_path}")

        frame_num += 1

    cap.release()
    print(f"Done. {frame_num} frames scanned, {detected} plates saved.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python processor.py <path/to/video.avi>")
        sys.exit(1)
    process_video(sys.argv[1])
