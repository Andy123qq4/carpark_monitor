# INPUT: path to .avi file (CLI arg)
# OUTPUT: OpenCV window with real-time plate detection overlay
# ROLE: live viewer — play video with ALPR running and bbox/label drawn on screen

import sys
import threading
import time

import cv2

import detection
import dedup

HOLD_FRAMES = 30  # keep bbox visible for N frames after last detection



def run(video_path: str, start_sec: float = 0.0, duration: float = 0.0):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    delay = max(1, int(1000 / fps))

    camera_id = detection.parse_camera_id(video_path)
    start_frame = max(0, int(start_sec * fps))
    end_frame = int((start_sec + duration) * fps) if duration > 0 else total_frames

    print(f"Viewer: {camera_id} | {fps:.0f} fps | {total_frames} frames")
    if duration > 0:
        print(f"Clip: {start_sec:.1f}s → {start_sec + duration:.1f}s  ({duration:.0f}s)")
    print("Controls: [Space] pause/resume  [Q/Esc] quit  [→] +5s  [←] -5s")

    # Create detector and temporal tracker
    detector = detection.ALPRDetector()
    tracker = dedup.TemporalTracker(hold_frames=HOLD_FRAMES)
    
    # Active overlays: plate_text -> {bbox, conf, ttl}
    active: dict[str, dict] = {}
    active_lock = threading.Lock()

    frame_num = start_frame
    if frame_num > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)

    # Background ALPR thread — processes frames without blocking display
    alpr_queue: list = []  # [(frame_copy, frame_num)] — only latest kept
    alpr_lock = threading.Lock()
    alpr_stop = threading.Event()

    def alpr_worker():
        """Background thread for ALPR processing with temporal deduplication."""
        while not alpr_stop.is_set():
            # Grab latest frame to process
            with alpr_lock:
                if alpr_queue:
                    work_frame, work_num = alpr_queue.pop()
                    alpr_queue.clear()  # discard stale frames
                else:
                    work_frame = None
            
            if work_frame is None:
                time.sleep(0.01)
                continue
            
            # Detect plates in frame
            timestamp_sec = work_num / fps
            raw = detector.detect_frame(work_frame)
            # TemporalTracker expects 4-tuples (text, conf, bbox, crop)
            detections = [(text, conf, bbox, None) for text, conf, bbox in raw]

            # Apply temporal tracking
            tracked = tracker.update(detections, work_num, timestamp_sec)
            
            # Update active overlays with new detections
            with active_lock:
                for text, conf, bbox, *_ in tracked:
                    active[text] = {"bbox": bbox, "conf": conf, "best_text": text, "ttl": HOLD_FRAMES}
                    print(f"  [{timestamp_sec:7.1f}s] {text}  {conf * 100:4.0f}%  bbox={bbox}")

    worker = threading.Thread(target=alpr_worker, daemon=True)
    worker.start()

    paused = False
    cv2.namedWindow("Carpark Viewer", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Carpark Viewer", 1280, 720)

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret or frame_num >= end_frame:
                break

            # Feed frame to ALPR background thread
            if frame_num % detector.frame_interval == 0:
                with alpr_lock:
                    alpr_queue.append((frame.copy(), frame_num))

            # Draw all active overlays
            with active_lock:
                for plate, info in list(active.items()):
                    # Use best_text (highest confidence reading) for display
                    display_text = info.get("best_text", plate)
                    detection.draw_bbox_label(frame, info["bbox"], f"{display_text} ({info['conf']*100:.0f}%)")
                # Decrement TTL and remove expired
                expired = [p for p, i in active.items() if i["ttl"] <= 0]
                for p in expired:
                    del active[p]
                for p in active:
                    active[p]["ttl"] -= 1

            # Timestamp + frame counter
            ts_sec = frame_num / fps
            h, m, s = int(ts_sec // 3600), int((ts_sec % 3600) // 60), int(ts_sec % 60)
            info_text = f"{h:02d}:{m:02d}:{s:02d}  F:{frame_num}"
            cv2.putText(frame, info_text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
            cv2.putText(frame, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

            cv2.imshow("Carpark Viewer", frame)
            frame_num += 1

        key = cv2.waitKey(delay if not paused else 50) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord(' '):
            paused = not paused
            print("PAUSED" if paused else "RESUMED")
        elif key == 83 or key == ord('d'):
            skip = int(5 * fps)
            frame_num = min(frame_num + skip, end_frame - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            with active_lock:
                active.clear()
        elif key == 81 or key == ord('a'):
            skip = int(5 * fps)
            frame_num = max(frame_num - skip, start_frame)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            with active_lock:
                active.clear()

    alpr_stop.set()
    cap.release()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python viewer.py <video_file> [--start SECONDS] [--duration SECONDS]")
        sys.exit(1)
    video = sys.argv[1]
    start = 0.0
    dur = 0.0
    if "--start" in sys.argv:
        idx = sys.argv.index("--start")
        start = float(sys.argv[idx + 1])
    if "--duration" in sys.argv:
        idx = sys.argv.index("--duration")
        dur = float(sys.argv[idx + 1])
    run(video, start_sec=start, duration=dur)
