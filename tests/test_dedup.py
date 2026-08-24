"""Tests for the per-platform upload dedup ledger in db_manager.

conftest.py points VIDEO_STUDIO_DB at a throwaway file before this import.
"""
import uuid

import db_manager


def _gen_id():
    return str(uuid.uuid4())


def test_not_uploaded_initially():
    gid = _gen_id()
    assert db_manager.is_platform_uploaded(gid, "youtube") is False
    assert db_manager.get_platform_upload(gid, "youtube") is None


def test_record_then_detected_as_uploaded():
    gid = _gen_id()
    db_manager.record_platform_upload(gid, "youtube", "yt_abc123")

    assert db_manager.is_platform_uploaded(gid, "youtube") is True
    row = db_manager.get_platform_upload(gid, "youtube")
    assert row["external_id"] == "yt_abc123"
    assert row["status"] == "completed"


def test_platforms_are_independent():
    gid = _gen_id()
    db_manager.record_platform_upload(gid, "youtube", "yt_1")
    assert db_manager.is_platform_uploaded(gid, "youtube") is True
    assert db_manager.is_platform_uploaded(gid, "instagram") is False


def test_recording_twice_is_idempotent():
    gid = _gen_id()
    db_manager.record_platform_upload(gid, "youtube", "first")
    db_manager.record_platform_upload(gid, "youtube", "second")

    # Still detected, and the latest id wins -- no duplicate rows / no crash.
    row = db_manager.get_platform_upload(gid, "youtube")
    assert row["external_id"] == "second"

    conn = db_manager.get_db_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM platform_uploads WHERE video_generation_id = ? AND platform = ?",
        (gid, "youtube"),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_failed_status_is_not_counted_as_uploaded():
    gid = _gen_id()
    db_manager.record_platform_upload(gid, "instagram", "", status="failed")
    assert db_manager.is_platform_uploaded(gid, "instagram") is False


def test_get_recent_topics_returns_newest_first():
    import time
    t1 = f"Topic Alpha {uuid.uuid4().hex[:6]}"
    t2 = f"Topic Beta {uuid.uuid4().hex[:6]}"
    db_manager.create_video_generation(_gen_id(), "p", t1, None, None, status="completed")
    time.sleep(0.01)
    db_manager.create_video_generation(_gen_id(), "p", t2, None, None, status="completed")
    recent = db_manager.get_recent_topics(10)
    assert t2 in recent and t1 in recent
    # Newest (t2) should appear before older (t1).
    assert recent.index(t2) < recent.index(t1)
