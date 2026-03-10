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
FRAME_INTERVAL = 5       # 从10改成5 -- 处理更多帧
MIN_CONFIDENCE = 0.3     # 从0.5降到0.3 -- 接受更多结果
DETECTION_DIR = Path("data/detections")

def save_annotated_frame(frame, bbox, text, conf, camera_id, frame_num):
    DETECTION_DIR.mkdir(parents=True, exist_ok=True)
    annotated = frame.copy()
    if bbox:
        x, y, w, h = bbox
        # Red bounding box (3px)
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 3)
        # Label with filled background
        label = f"{text} ({conf*100:.0f}%)"
        font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2
        (lw, lh), baseline = cv2.getTextSize(label, font, scale, thickness)
        label_y = max(y - 4, lh + 4)  # don't go off top edge
        cv2.rectangle(annotated, (x, label_y - lh - baseline), (x + lw, label_y), (0, 0, 255), -1)
        cv2.putText(annotated, label, (x, label_y - baseline), font, scale, (255, 255, 255), thickness)

        # Also save cropped plate patch for verification
        pad = 4
        crop = frame[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
        if crop.size > 0:
            crop_path = DETECTION_DIR / f"{camera_id}_{frame_num}_{text}_crop.jpg"
            cv2.imwrite(str(crop_path), crop)

    filename = DETECTION_DIR / f"{camera_id}_{frame_num}_{text}.jpg"
    cv2.imwrite(str(filename), annotated)
    return filename

def parse_camera_id(video_path: str) -> str:
    """Extract camera ID from filename, e.g. 'GF15 ...' -> 'GF15'"""
    name = Path(video_path).stem
    return name.split()[0] if ' ' in name else name

def process_video(video_path: str):
    db.init_db()
    camera_id = parse_camera_id(video_path)
    video_file = Path(video_path).name

    alpr = ALPR(
        detector_model="yolo-v9-t-640-license-plate-end2end",
        detector_conf_thresh=0.4,  # 从0.6降到0.4 -- YOLO更敏感
        detector_providers=['CPUExecutionProvider'],
    )
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

                # Extract bounding box coordinates from plate detection
                bbox = None
                if hasattr(result, 'detection') and result.detection is not None:
                    if hasattr(result.detection, 'bounding_box'):
                        plate_bbox = result.detection.bounding_box
                        if plate_bbox is not None:
                            # Convert to x, y, w, h format
                            x = int(plate_bbox.x1)
                            y = int(plate_bbox.y1)
                            w = int(plate_bbox.x2 - plate_bbox.x1)
                            h = int(plate_bbox.y2 - plate_bbox.y1)
                            bbox = (x, y, w, h)

                timestamp_sec = frame_num / fps
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
