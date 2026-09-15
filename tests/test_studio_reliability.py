"""Regression tests for edits, deletion ownership, queue recovery and publishing."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import asset_state
import backend
import cost_tracker
import db_manager
import job_queue


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "studio.db"))
    db_manager.init_db()
    job_queue.initialize()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "temp").mkdir()
    (tmp_path / "outputs").mkdir()
    return tmp_path


def saved_scene():
    request = backend.RenderRequest(generation_id="g", image_provider="local", storyboard=[
        {"scene": 1, "narration": "Old words", "visual_prompt": "An ocean", "speaker": "Sarah"}
    ])
    scenes = asset_state.prepare_storyboard(request, {})
    scenes[0].update(audio_path="temp/voice.wav", image_path="temp/image.png")
    return request, {"storyboard": scenes}


def test_unchanged_assets_resume_but_narration_edit_invalidates_only_audio():
    request, generation = saved_scene()
    unchanged = asset_state.prepare_storyboard(request, generation)[0]
    assert unchanged["audio_path"] == "temp/voice.wav"
    request.storyboard[0]["narration"] = "New words"
    edited = asset_state.prepare_storyboard(request, generation)[0]
    assert "audio_path" not in edited
    assert edited["image_path"] == "temp/image.png"


@pytest.mark.parametrize("field,value", [("speed", 1.2), ("local_image_model", "other-model"), ("image_provider", "leonardo")])
def test_changed_render_settings_invalidate_corresponding_assets(field, value):
    request, generation = saved_scene()
    setattr(request, field, value)
    scene = asset_state.prepare_storyboard(request, generation)[0]
    assert ("audio_path" if field == "speed" else "image_path") not in scene


def test_client_cannot_supply_arbitrary_asset_paths():
    request, _ = saved_scene()
    request.storyboard[0]["audio_path"] = "/etc/passwd"
    assert "audio_path" not in asset_state.prepare_storyboard(request, {})[0]


def test_deletion_keeps_neighbor_shared_and_external_files(database):
    own = database / "temp/image_1700000000.png"
    neighbor = database / "temp/image_1700000001.png"
    shared = database / "temp/shared.wav"
    outside = database / "private.txt"
    for path in (own, neighbor, shared, outside):
        path.write_text("keep unless owned")
    db_manager.create_video_generation("one", "p", "t", {}, [
        {"image_path": str(own), "audio_path": str(shared), "clip_path": str(outside)}])
    db_manager.create_video_generation("two", "p", "t", {}, [{"image_path": str(neighbor), "audio_path": str(shared)}])
    db_manager.delete_video_generation("one")
    assert not own.exists()
    assert all(path.exists() for path in (neighbor, shared, outside))


def test_queue_claims_duplicate_submission_and_keeps_payload(database):
    job_queue.enqueue("render", "one", {"generation_id": "one", "speed": 1.2})
    with pytest.raises(job_queue.JobConflict):
        job_queue.enqueue("render", "one", {})
    seen = []
    job_queue.drain({"render": seen.append})
    assert seen == [{"generation_id": "one", "speed": 1.2}]
    assert not job_queue.active("one")


def test_restart_retains_queued_jobs_and_marks_interrupted_work(database):
    for name in ("queued", "running"):
        db_manager.create_video_generation(name, "p", "t", {}, [], status="rendering")
        job_queue.enqueue("render", name, {})
    with db_manager.get_db_connection() as conn:
        conn.execute("UPDATE work_jobs SET status='running' WHERE resource_id='running'")
    conn.close()
    job_queue.recover_interrupted()
    assert db_manager.get_video_generation("running")["status"] == "failed"
    assert "restarted" in db_manager.get_video_generation("running")["error_message"]
    assert job_queue.active("queued")
    assert not job_queue.active("running")


def test_concurrent_upload_reservations_have_only_one_winner(database):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: db_manager.reserve_platform_upload("g", "youtube"), range(4)))
    assert results.count(True) == 1


def test_paid_budget_is_reserved_before_concurrent_calls(database, monkeypatch):
    monkeypatch.setenv("LEONARDO_DAILY_BUDGET", "1")
    monkeypatch.setenv("LEONARDO_IMAGE_COST", "1")
    called = []
    def attempt(_):
        try:
            cost_tracker.run_paid("g", "image", lambda: called.append(True))
            return True
        except cost_tracker.BudgetExceededError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count(True) == 1
    assert len(called) == 1


def test_free_provider_has_no_leonardo_estimate():
    assert cost_tracker.estimate_render_cost(5, "Cinematic Slideshow", provider="local") == 0


def test_image_regeneration_uses_selected_provider_and_is_reusable(database, monkeypatch):
    image = database / "temp/local.png"
    image.write_bytes(b"image")
    db_manager.create_video_generation("g", "p", "t", {}, [{
        "scene": 1, "narration": "Hello", "visual_prompt": "Ocean", "speaker": "Sarah",
    }])
    called = []
    monkeypatch.setattr(backend.image_providers, "generate_image",
                        lambda provider, *args: (called.append(provider), (str(image), None))[1])
    monkeypatch.setattr(backend, "generate_leonardo_image", lambda *args: pytest.fail("Wrong provider"))
    response = TestClient(backend.app).post("/api/regenerate-scene-asset", json={
        "generation_id": "g", "scene_index": 0, "asset_type": "image", "image_provider": "local",
    })
    assert response.status_code == 200
    assert called == ["local"]
    generation = db_manager.get_video_generation("g")
    request = backend.RenderRequest(generation_id="g", image_provider="local", storyboard=generation["storyboard"])
    assert asset_state.prepare_storyboard(request, generation)[0]["image_path"] == str(image)


def test_busy_generation_cannot_be_deleted(database):
    db_manager.create_video_generation("g", "p", "t", {}, [], status="rendering")
    with pytest.raises(ValueError, match="finish"):
        db_manager.delete_video_generation("g")


def test_queue_submissions_do_not_block_status_threads(database):
    import threading
    entered, release = threading.Event(), threading.Event()
    processed = []
    def handler(payload):
        if payload["id"] == "first":
            entered.set()
            assert release.wait(3)
        processed.append(payload["id"])
    job_queue.enqueue("render", "first", {"id": "first"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker = pool.submit(job_queue.drain, {"render": handler})
        assert entered.wait(2)
        try:
            job_queue.enqueue("render", "second", {"id": "second"})
            pool.submit(job_queue.drain, {"render": handler}).result(timeout=1)
        finally:
            release.set()
        worker.result(timeout=2)
    assert processed == ["first", "second"]


def test_cleanup_preserves_failed_render_assets(database):
    import os
    import time
    asset = database / "temp/saved.wav"
    asset.write_bytes(b"audio")
    old = time.time() - 100 * 3600
    os.utime(asset, (old, old))
    db_manager.create_video_generation("g", "p", "t", {}, [{"audio_path": str(asset)}], status="failed")
    assert backend.cleanup_stale_temp_files() == 0
    assert asset.exists()


def test_regeneration_guard_excludes_a_render(database):
    with job_queue.resource_guard("g"):
        with pytest.raises(job_queue.JobConflict):
            job_queue.enqueue("render", "g", {})
    assert not job_queue.active("g")


def test_failure_before_first_scene_preserves_editor_changes(database, monkeypatch):
    db_manager.create_video_generation("g", "p", "t", {}, [
        {"scene": 1, "narration": "Before", "visual_prompt": "Ocean"}])
    def fail(**kwargs):
        raise RuntimeError("Provider unavailable")
    monkeypatch.setattr(backend, "run_viral_shorts_pipeline_new", fail)
    monkeypatch.setattr(backend, "notify", lambda *a, **k: None)
    request = backend.RenderRequest(generation_id="g", storyboard=[
        {"scene": 1, "narration": "After", "visual_prompt": "Ocean"}])
    with pytest.raises(RuntimeError, match="unavailable"):
        backend.run_render_task("g", request)
    saved = db_manager.get_video_generation("g")
    assert saved["storyboard"][0]["narration"] == "After"
    assert saved["status"] == "failed"
    assert "unavailable" in saved["error_message"]
