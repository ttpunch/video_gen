"""The quality settings must survive the trip from the UI payload to ffmpeg.

These endpoints are the seam where a renamed or forgotten field silently falls
back to a default, so the render quietly ignores what the user chose.
"""
import pytest
from fastapi.testclient import TestClient

import backend
import video_quality as vq


@pytest.fixture
def client():
    return TestClient(backend.app)


def test_config_advertises_the_quality_presets_the_ui_renders(client):
    body = client.get("/api/config").json()
    assert body["quality_presets"] == list(vq.QUALITY_PRESETS)
    assert body["default_quality"] == vq.DEFAULT_QUALITY
    assert body["motion_styles"] == ["Dynamic", "Subtle", "Off"]
    assert body["delivery"]["fps"] == vq.FPS
    assert body["delivery"]["target_lufs"] == vq.TARGET_LUFS


def test_render_endpoint_forwards_every_quality_option(client, monkeypatch):
    captured = {}

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        return "/tmp/out.mp4", [], "topic", {}

    monkeypatch.setattr(backend, "run_viral_shorts_pipeline_new", fake_pipeline)
    monkeypatch.setattr(backend.db_manager, "get_video_generation",
                        lambda _id: {"script_data": {}, "storyboard": []})
    monkeypatch.setattr(backend.db_manager, "update_video_generation",
                        lambda *a, **k: None)

    payload = {
        "generation_id": "gen-1",
        "storyboard": [{"narration": "hi", "visual_prompt": "x"}],
        "quality": "Maximum",
        "motion_style": "Subtle",
        "progress_bar": False,
        "normalize_audio": False,
        "duck_music": False,
        "enable_thumbnail": False,
        "subscribe_overlay": False,
        "channel_handle": "@mychannel",
    }
    assert client.post("/api/render-storyboard", json=payload).status_code == 200

    for field, expected in payload.items():
        if field in ("generation_id", "storyboard"):
            continue
        assert captured[field] == expected, f"{field} did not reach the pipeline"


def test_render_endpoint_defaults_match_the_module_defaults(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(backend, "run_viral_shorts_pipeline_new",
                        lambda **kw: (captured.update(kw), ("/tmp/o.mp4", [], "t", {}))[1])
    monkeypatch.setattr(backend.db_manager, "get_video_generation",
                        lambda _id: {"script_data": {}, "storyboard": []})
    monkeypatch.setattr(backend.db_manager, "update_video_generation",
                        lambda *a, **k: None)

    client.post("/api/render-storyboard",
                json={"generation_id": "g", "storyboard": []})

    assert captured["quality"] == vq.DEFAULT_QUALITY
    assert captured["motion_style"] == "Dynamic"
    assert captured["normalize_audio"] is True
    assert captured["duck_music"] is True


def test_shorts_burn_in_a_progress_bar_by_default():
    """Shorts hide the scrubber, so the burnt-in retention bar is the only cue."""
    assert backend.RenderRequest(generation_id="g", storyboard=[]).progress_bar is True


def test_generation_status_exposes_the_thumbnail(client, monkeypatch, tmp_path):
    video = tmp_path / "viral_reel_1.mp4"
    video.write_bytes(b"video")
    thumb = tmp_path / "viral_reel_1_thumb.jpg"
    thumb.write_bytes(b"jpeg")

    monkeypatch.setattr(backend.db_manager, "get_video_generation", lambda _id: {
        "status": "completed", "final_video_path": str(video),
        "storyboard": [], "script_data": {},
    })

    body = client.get("/api/generation-status/gen-1").json()
    assert body["thumbnail_url"].endswith("viral_reel_1_thumb.jpg")
    assert body["video_url"].endswith("viral_reel_1.mp4")


def test_generation_status_omits_a_thumbnail_that_was_never_made(client, monkeypatch, tmp_path):
    video = tmp_path / "viral_reel_2.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(backend.db_manager, "get_video_generation", lambda _id: {
        "status": "completed", "final_video_path": str(video),
        "storyboard": [], "script_data": {},
    })
    assert client.get("/api/generation-status/gen-2").json()["thumbnail_url"] == ""


def test_draft_preserves_the_stock_tags_the_render_depends_on(client, monkeypatch):
    """The draft endpoint used to rebuild scene dicts field-by-field.

    `visual_source` and `stock_query` were not in that list, so every storyboard
    drafted through the UI reached the renderer untagged and fell back to image
    generation -- while a hand-tagged storyboard used real footage. Same code,
    opposite result, which is exactly the discrepancy a user noticed.
    """
    monkeypatch.setattr(backend, "generate_validated_script", lambda *a, **k: {
        "topic": "t",
        "scenes": [
            {"speaker": "Sarah", "narration": "n1", "visual_prompt": "v1",
             "visual_source": "stock", "stock_query": "ocean waves"},
            {"speaker": "Sarah", "narration": "n2", "visual_prompt": "v2",
             "visual_source": "generate"},
        ],
    })
    monkeypatch.setattr(backend.db_manager, "create_video_generation",
                        lambda *a, **k: None)

    body = client.post("/api/draft-script",
                       json={"prompt": "p", "model": "m"}).json()
    sb = body["storyboard"]
    assert sb[0]["visual_source"] == "stock"
    assert sb[0]["stock_query"] == "ocean waves"
    assert sb[1]["visual_source"] == "generate"


def test_drafted_scenes_still_carry_the_fields_the_editor_needs(client, monkeypatch):
    monkeypatch.setattr(backend, "generate_validated_script", lambda *a, **k: {
        "topic": "t",
        "scenes": [{"speaker": "Sarah", "narration": "n", "visual_prompt": "v",
                    "visual_source": "stock", "stock_query": "q"}],
    })
    monkeypatch.setattr(backend.db_manager, "create_video_generation",
                        lambda *a, **k: None)
    scene = client.post("/api/draft-script",
                        json={"prompt": "p", "model": "m"}).json()["storyboard"][0]
    for key in ("scene", "speaker", "narration", "visual_prompt",
                "image_url", "image_path", "audio_url", "audio_path", "duration"):
        assert key in scene, f"draft dropped {key}"


# --------------------------------------------------------------------------
# Model list ordering
# --------------------------------------------------------------------------
#
# The UI selects the first entry by default. The list previously force-pinned a
# cloud model to the front, so an exhausted weekly quota made every manual draft
# fail on a model the user never chose. Ollama reports cloud models with size 0.

def _tags(models):
    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"models": models}
    return R()


def test_local_models_are_offered_before_cloud_models(monkeypatch):
    monkeypatch.setattr(backend.requests, "get", lambda *a, **k: _tags([
        {"name": "minimax-m3:cloud", "size": 0},
        {"name": "qwen2.5:7b-instruct", "size": 4_700_000_000},
        {"name": "glm-5:cloud", "size": 0},
    ]))
    assert backend.get_ollama_models()[0] == "qwen2.5:7b-instruct"


def test_largest_local_model_is_the_default(monkeypatch):
    """Size is the best available proxy for quality on one machine."""
    monkeypatch.setattr(backend.requests, "get", lambda *a, **k: _tags([
        {"name": "small:0.8b", "size": 1_000_000_000},
        {"name": "big:7b", "size": 4_700_000_000},
    ]))
    assert backend.get_ollama_models()[0] == "big:7b"


def test_embedding_models_are_not_offered(monkeypatch):
    """An embedding model produces a confusing failure, not a script."""
    monkeypatch.setattr(backend.requests, "get", lambda *a, **k: _tags([
        {"name": "nomic-embed-text:latest", "size": 300_000_000},
        {"name": "qwen2.5:7b-instruct", "size": 4_700_000_000},
    ]))
    assert "nomic-embed-text:latest" not in backend.get_ollama_models()


def test_cloud_fallbacks_still_available_when_ollama_is_down(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(backend.requests, "get", boom)
    models = backend.get_ollama_models()
    assert "minimax-m3:cloud" in models
