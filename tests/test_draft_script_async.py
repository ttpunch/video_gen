"""/api/draft-script runs as a background job, not a synchronous request.

Reproduced live: POST /api/draft-script with a local Ollama model and
enable_search=true produced no response in 280s -- the endpoint was
synchronous with no way to report progress or an intermediate timeout, so a
client had no choice but to give up and guess whether the backend was still
working or had silently died.

TestClient runs FastAPI background tasks to completion before .post()
returns, so these tests exercise the real code path end to end (including
run_draft_task and the db_manager writes it makes) rather than mocking the
background execution away.
"""
import pytest
from fastapi.testclient import TestClient

import backend
import db_manager


@pytest.fixture
def client():
    return TestClient(backend.app)


def test_draft_script_returns_immediately_with_a_drafting_status(client, monkeypatch):
    monkeypatch.setattr(backend, "generate_validated_script", lambda *a, **k: {
        "topic": "t", "scenes": [{"speaker": "Sarah", "narration": "n", "visual_prompt": "v"}],
    })
    created = {}
    monkeypatch.setattr(backend.db_manager, "create_video_generation",
                        lambda gen_id, *a, **k: created.update(gen_id=gen_id, status=k.get("status")))
    monkeypatch.setattr(backend.db_manager, "update_video_generation", lambda *a, **k: None)

    resp = client.post("/api/draft-script", json={"prompt": "p", "model": "m"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "drafting"
    assert body["generation_id"]
    # The immediate DB row is the 'drafting' placeholder, not the finished draft.
    assert created["status"] == "drafting"


def test_generation_status_reports_the_finished_draft(client, monkeypatch):
    monkeypatch.setattr(backend, "generate_validated_script", lambda *a, **k: {
        "topic": "octopus facts",
        "scenes": [{"speaker": "Sarah", "narration": "n", "visual_prompt": "v",
                    "visual_source": "stock", "stock_query": "octopus"}],
    })

    resp = client.post("/api/draft-script", json={"prompt": "octopus facts", "model": "m"})
    gen_id = resp.json()["generation_id"]

    status = client.get(f"/api/generation-status/{gen_id}").json()
    assert status["status"] == "draft"
    assert status["topic"] == "octopus facts"
    assert status["storyboard"][0]["stock_query"] == "octopus"

    db_manager.delete_video_generation(gen_id)


def test_generation_status_reports_a_failed_draft_with_the_real_error(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("the model did not return a usable story")

    monkeypatch.setattr(backend, "generate_validated_script", boom)

    resp = client.post("/api/draft-script", json={"prompt": "p", "model": "m"})
    gen_id = resp.json()["generation_id"]

    status = client.get(f"/api/generation-status/{gen_id}").json()
    assert status["status"] == "failed"
    assert "usable story" in status["error_message"]
    assert any("usable story" in line for line in status["logs"])

    db_manager.delete_video_generation(gen_id)


def test_generation_status_exposes_progress_logs_during_drafting(client, monkeypatch):
    """The logs written during generation (search/story/storyboard stages)
    must be readable through the same endpoint the frontend polls, not just
    printed to the server's own stdout."""
    def fake_generate(prompt, model, hook_style, enable_search, art_style,
                      duration_preset, log=print):
        log("Drafting script (attempt 1/3)...")
        log("Story generated.")
        return {"topic": "t", "scenes": [{"speaker": "Sarah", "narration": "n", "visual_prompt": "v"}]}

    monkeypatch.setattr(backend, "generate_validated_script", fake_generate)

    resp = client.post("/api/draft-script", json={"prompt": "p", "model": "m"})
    gen_id = resp.json()["generation_id"]

    status = client.get(f"/api/generation-status/{gen_id}").json()
    assert any("attempt 1/3" in line for line in status["logs"])
    assert any("Story generated" in line for line in status["logs"])

    db_manager.delete_video_generation(gen_id)


def test_generation_status_surfaces_validation_warnings_from_the_deadline_fallback(client, monkeypatch):
    """When generate_validated_script returns its least-bad attempt (the
    overall-deadline fallback), the warnings must reach the client instead of
    silently presenting a flawed script as a clean success."""
    monkeypatch.setattr(backend, "generate_validated_script", lambda *a, **k: {
        "topic": "t",
        "scenes": [{"speaker": "Sarah", "narration": "n", "visual_prompt": "v"}],
        "_validation_warnings": ["script too short (40 words; need >= 110)"],
    })

    resp = client.post("/api/draft-script", json={"prompt": "p", "model": "m"})
    gen_id = resp.json()["generation_id"]

    status = client.get(f"/api/generation-status/{gen_id}").json()
    assert status["status"] == "draft"
    assert any("too short" in w for w in status["validation_warnings"])

    db_manager.delete_video_generation(gen_id)
