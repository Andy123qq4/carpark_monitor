# INPUT: video frames from OpenCV
# OUTPUT: plate detections with text, confidence, bounding box
# ROLE: core ALPR detection module — single source of truth for plate recognition

import contextlib
import io
import logging
import os
import re
import requests
import time
from pathlib import Path

import cv2
import numpy as np
from fast_alpr import ALPR
from fast_alpr.alpr import ALPRResult

import dedup

# Suppress noisy CoreML/ONNX fallback messages (empty tensor on frames with no plates)
logging.getLogger("open_image_models").setLevel(logging.CRITICAL)


@contextlib.contextmanager
def _suppress_stderr():
    """Redirect C++ stderr to /dev/null — used during ONNX inference calls."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    old = os.dup(2)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        os.dup2(old, 2)
        os.close(old)
        os.close(devnull)

# Configuration
# HK standard plates exclude I, O, Q (confused with 1, 0)
HK_PLATE_RE = re.compile(r'^[A-HJ-NP-Z]{1,2}\s?[0-9]{1,4}$')
FRAME_INTERVAL = 1       # process every Nth frame (1=every frame for max detection density)
MIN_CONFIDENCE = 0.7     # confidence threshold for detections

_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def _apply_clahe(crop: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = _CLAHE.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _predict_with_clahe(alpr, frame: np.ndarray) -> list:
    plate_detections = alpr.detector.predict(frame)
    out = []
    for detection in plate_detections:
        bbox = detection.bounding_box
        x1, y1 = max(int(bbox.x1), 0), max(int(bbox.y1), 0)
        x2, y2 = min(int(bbox.x2), frame.shape[1]), min(int(bbox.y2), frame.shape[0])
        crop = frame[y1:y2, x1:x2]
        if crop.size > 0:
            crop = _apply_clahe(crop)
        ocr_result = alpr.ocr.predict(crop)
        out.append(ALPRResult(detection=detection, ocr=ocr_result))
    return out


class ALPRDetector:
    """Encapsulates ALPR detection logic with deduplication."""
    
    def __init__(self, 
                 frame_interval: int = FRAME_INTERVAL,
                 min_confidence: float = MIN_CONFIDENCE,
                 use_coreml: bool = True):
        """Initialize ALPR detector with Apple Silicon acceleration.
        
        Args:
            frame_interval: Process every Nth frame (default: 3)
            min_confidence: Minimum confidence threshold (default: 0.7)
            use_coreml: Use CoreML (Apple Neural Engine) if available (default: True)
        """
        self.frame_interval = frame_interval
        self.min_confidence = min_confidence
        
        providers = ['CoreMLExecutionProvider', 'CPUExecutionProvider'] if use_coreml else ['CPUExecutionProvider']
        with _suppress_stderr(), contextlib.redirect_stderr(io.StringIO()):
            self.alpr = ALPR(
                detector_model="yolo-v9-t-640-license-plate-end2end",
                detector_conf_thresh=0.4,
                detector_providers=providers,
            )
    
    def detect_frame(self, frame) -> list[tuple[str, float, tuple]]:
        """Detect plates in a single frame.
        
        Args:
            frame: OpenCV frame (numpy array)
            
        Returns:
            List of (plate_text, confidence, bbox) tuples
            bbox is (x, y, w, h) or None
        """
        with _suppress_stderr():
            results = _predict_with_clahe(self.alpr, frame)
        detections = []
        
        for result in results:
            if result.ocr is None:
                continue
            
            text = result.ocr.text.upper().strip()
            conf = result.ocr.confidence
            if isinstance(conf, list):
                conf = sum(conf) / len(conf) if conf else 0.0
            
            # Validate HK plate format
            if not HK_PLATE_RE.match(text):
                continue
            
            # Extract bounding box
            bbox = None
            if hasattr(result, 'detection') and result.detection is not None:
                if hasattr(result.detection, 'bounding_box'):
                    pb = result.detection.bounding_box
                    if pb is not None:
                        bbox = (int(pb.x1), int(pb.y1), 
                               int(pb.x2 - pb.x1), int(pb.y2 - pb.y1))
            
            detections.append((text, conf, bbox))
        
        # Apply confidence threshold and frame-level deduplication
        detections = dedup.apply_confidence_threshold(detections, self.min_confidence)
        detections = dedup.deduplicate_detections(detections)
        return detections
    

def draw_bbox_label(frame, bbox, label: str) -> None:
    """Draw red bbox + label overlay on frame in-place."""
    if bbox is None:
        return
    x, y, w, h = bbox
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
    font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2
    (lw, lh), bl = cv2.getTextSize(label, font, scale, thick)
    ly = max(y - 4, lh + 4)
    cv2.rectangle(frame, (x, ly - lh - bl), (x + lw, ly), (0, 0, 255), -1)
    cv2.putText(frame, label, (x, ly - bl), font, scale, (255, 255, 255), thick)


def parse_camera_id(video_path: str) -> str:
    name = Path(video_path).stem
    return name.split()[0] if ' ' in name else name


PLATE_RECOGNIZER_TOKEN = os.environ.get("PLATE_RECOGNIZER_API", "")
PLATE_RECOGNIZER_URL = "https://api.platerecognizer.com/v1/plate-reader/"


def recognize_crop(crop) -> tuple[str, float] | None:
    """Send a plate crop image to Plate Recognizer API for accurate OCR."""
    if crop is None or crop.size == 0:
        return None
    if not PLATE_RECOGNIZER_TOKEN:
        return None
    _, jpg = cv2.imencode(".jpg", crop)
    for attempt in range(3):
        try:
            resp = requests.post(
                PLATE_RECOGNIZER_URL,
                files={"upload": jpg.tobytes()},
                data={"regions": "hk"},
                headers={"Authorization": f"Token {PLATE_RECOGNIZER_TOKEN}"},
                timeout=15,
            )
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(2 ** attempt)
    else:
        return None
    results = resp.json().get("results", [])
    if not results:
        return None
    best = max(results, key=lambda r: r["score"])
    text = best["plate"].upper().strip()
    conf = float(best["score"])
    if not HK_PLATE_RE.match(text):
        return None
    return (text, conf)


class PlateRecognizerDetector:
    def __init__(self,
                 frame_interval: int = FRAME_INTERVAL,
                 min_confidence: float = MIN_CONFIDENCE):
        self.frame_interval = frame_interval
        self.min_confidence = min_confidence
        if not PLATE_RECOGNIZER_TOKEN:
            raise RuntimeError("PLATE_RECOGNIZER_API env var not set")

    def detect_frame(self, frame) -> list[tuple[str, float, tuple]]:
        _, jpg = cv2.imencode(".jpg", frame)
        for attempt in range(3):
            try:
                resp = requests.post(
                    PLATE_RECOGNIZER_URL,
                    files={"upload": jpg.tobytes()},
                    data={"regions": "hk"},
                    headers={"Authorization": f"Token {PLATE_RECOGNIZER_TOKEN}"},
                    timeout=15,
                )
                if resp.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    return []
                time.sleep(2 ** attempt)
        else:
            return []
        detections = []
        for r in resp.json().get("results", []):
            text = r["plate"].upper().strip()
            conf = float(r["score"])
            if conf < self.min_confidence:
                continue
            if not HK_PLATE_RE.match(text):
                continue
            box = r.get("box", {})
            bbox = None
            if box:
                x1, y1, x2, y2 = box["xmin"], box["ymin"], box["xmax"], box["ymax"]
                bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            detections.append((text, conf, bbox))
        detections = dedup.apply_confidence_threshold(detections, self.min_confidence)
        detections = dedup.deduplicate_detections(detections)
        return detections
