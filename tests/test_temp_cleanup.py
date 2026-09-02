"""cleanup_stale_temp_files: temp/ debris from failed or abandoned runs
(orphaned video_list/audio_list/merged_*/scene_*/voice_raw_* files) must not
accumulate forever, but must never touch a file a draft or in-progress render
still references.
"""
import os
import time

import backend


def _age_file(path, hours_old):
    old_time = time.time() - hours_old * 3600
    os.utime(path, (old_time, old_time))


def test_cleanup_removes_only_files_older_than_the_max_age(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp")
    old_file = tmp_path / "temp" / "merged_video_111.mp4"
    new_file = tmp_path / "temp" / "merged_video_222.mp4"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")
    _age_file(old_file, hours_old=49)
    _age_file(new_file, hours_old=1)

    monkeypatch.setattr(backend.db_manager, "list_video_generations", lambda: [])

    deleted = backend.cleanup_stale_temp_files(max_age_hours=48)

    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_preserves_files_a_draft_or_render_still_references(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp")
    referenced = tmp_path / "temp" / "voice_raw_999.wav"
    referenced.write_bytes(b"audio")
    _age_file(referenced, hours_old=100)  # old enough to be deleted if unreferenced

    monkeypatch.setattr(backend.db_manager, "list_video_generations", lambda: [
        {
            "status": "rendering",
            "storyboard": [{"audio_path": str(referenced)}],
        }
    ])

    deleted = backend.cleanup_stale_temp_files(max_age_hours=48)

    assert deleted == 0
    assert referenced.exists()


def test_cleanup_checks_draft_and_drafting_status_too(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp")
    referenced = tmp_path / "temp" / "scene_vid_1_0.mp4"
    referenced.write_bytes(b"video")
    _age_file(referenced, hours_old=100)

    monkeypatch.setattr(backend.db_manager, "list_video_generations", lambda: [
        {"status": "draft", "storyboard": [{"image_path": str(referenced)}]},
    ])

    assert backend.cleanup_stale_temp_files(max_age_hours=48) == 0
    assert referenced.exists()


def test_cleanup_skips_entirely_when_the_db_read_fails(tmp_path, monkeypatch):
    """Deleting anything is worse than deleting nothing when we can't tell
    what's still in use -- skip the whole run rather than guess."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp")
    old_file = tmp_path / "temp" / "merged_video_111.mp4"
    old_file.write_bytes(b"old")
    _age_file(old_file, hours_old=100)

    def boom():
        raise RuntimeError("db locked")

    monkeypatch.setattr(backend.db_manager, "list_video_generations", boom)

    deleted = backend.cleanup_stale_temp_files(max_age_hours=48)

    assert deleted == 0
    assert old_file.exists()


def test_cleanup_ignores_a_missing_temp_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No temp/ directory created at all.
    assert backend.cleanup_stale_temp_files(max_age_hours=48) == 0


def test_cleanup_does_not_touch_subdirectories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp/logs")
    _age_file(tmp_path / "temp" / "logs", hours_old=100)
    monkeypatch.setattr(backend.db_manager, "list_video_generations", lambda: [])

    # Must not raise on a directory entry, and must not remove it.
    backend.cleanup_stale_temp_files(max_age_hours=48)
    assert (tmp_path / "temp" / "logs").is_dir()
