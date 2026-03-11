import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import db


def _make_session(plate, ts, bbox_x, bbox_y, conf=0.9, video="GF18.mp4", frame=0):
    """Helper: build a session dict matching merge_stationary_sessions() input format."""
    det = {
        "video_file": video, "camera_id": "GF18", "frame_num": frame,
        "timestamp_sec": ts, "plate_text": plate, "confidence": conf,
        "bbox_x": bbox_x, "bbox_y": bbox_y, "bbox_w": 50, "bbox_h": 30,
    }
    return {"detection": det, "frame_count": 1, "is_stationary": False}


def test_no_sessions_returns_empty():
    assert db.merge_stationary_sessions([]) == []


def test_single_session_unchanged():
    sessions = [_make_session("WB6066", 100, 840, 800)]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["is_stationary"] is False


def test_two_sessions_same_spot_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("WB6066", 200, 842, 805),  # 14px apart, 100s gap
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["is_stationary"] is True
    assert result[0]["detection"]["timestamp_sec"] == 100  # earliest


def test_two_sessions_different_spot_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("WB6066", 200, 1400, 700),  # 560px apart
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2
    assert all(not s["is_stationary"] for s in result)


def test_two_sessions_too_far_apart_in_time_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("WB6066", 100 + 1801, 842, 805),  # >30 min gap
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2
    assert all(not s["is_stationary"] for s in result)


def test_different_plates_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("VH703",  200, 842, 805),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2
    assert all(not s["is_stationary"] for s in result)


def test_different_videos_not_merged():
    sessions = [
        _make_session("WB6066", 100, 840, 800, video="GF18.mp4"),
        _make_session("WB6066", 200, 842, 805, video="GF15.mp4"),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 2


def test_merge_picks_highest_confidence_detection():
    sessions = [
        _make_session("WB6066", 100, 840, 800, conf=0.75),
        _make_session("WB6066", 200, 842, 805, conf=0.95),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["detection"]["confidence"] == 0.95


def test_merge_keeps_earliest_timestamp():
    sessions = [
        _make_session("WB6066", 200, 840, 800),
        _make_session("WB6066", 100, 842, 805),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert len(result) == 1
    assert result[0]["detection"]["timestamp_sec"] == 100


def test_frame_count_summed():
    s1 = _make_session("WB6066", 100, 840, 800)
    s2 = _make_session("WB6066", 200, 842, 805)
    s1["frame_count"] = 3
    s2["frame_count"] = 5
    result = db.merge_stationary_sessions([s1, s2])
    assert result[0]["frame_count"] == 8


def test_output_sorted_descending_by_timestamp():
    sessions = [
        _make_session("WB6066", 100, 840, 800),
        _make_session("VH703",  300, 100, 100),
    ]
    result = db.merge_stationary_sessions(sessions)
    assert result[0]["detection"]["timestamp_sec"] > result[1]["detection"]["timestamp_sec"]
