# INPUT: video frames from OpenCV
# OUTPUT: plate detections with text, confidence, bounding box
# ROLE: core ALPR detection module — single source of truth for plate recognition

import contextlib
import io
import logging
import os
import re
from pathlib import Path

import cv2
from fast_alpr import ALPR

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
HK_PLATE_RE = re.compile(r'^[A-Z]{1,2}\s?[0-9]{1,4}$')
FRAME_INTERVAL = 1       # process every Nth frame (1=every frame for max detection density)
MIN_CONFIDENCE = 0.7     # confidence threshold for detections


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
            results = self.alpr.predict(frame)
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
    """Extract camera ID from filename, e.g. 'GF15 ...' -> 'GF15'"""
    name = Path(video_path).stem
    return name.split()[0] if ' ' in name else name
