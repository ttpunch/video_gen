"""Tests for the YouTube upload path's synthetic-media disclosure.

YouTube's "Altered or Synthetic Content" policy went into full enforcement in
January 2026 and is enforced via ``status.containsSyntheticMedia`` on the Data
API. The app had zero handling for it -- every upload silently omitted the
field regardless of whether the video's visuals came from real stock footage
or AI image generation.
"""
import backend
import uploader_youtube as uy


class _FakeRequest:
    def __init__(self, body):
        self.body = body
    def next_chunk(self):
        return None, {"id": "fake-video-id"}


class _FakeVideosResource:
    def __init__(self, capture):
        self.capture = capture
    def insert(self, part, body, media_body):
        self.capture["body"] = body
        return _FakeRequest(body)


class _FakeService:
    def __init__(self, capture):
        self._videos = _FakeVideosResource(capture)
    def videos(self):
        return self._videos


def _upload(monkeypatch, tmp_path, **kwargs):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake video bytes")
    capture = {}
    monkeypatch.setattr(uy, "get_youtube_service", lambda: _FakeService(capture))
    monkeypatch.setattr(uy, "MediaFileUpload", lambda *a, **k: object())
    uy.upload_video_to_youtube(str(video), "title", "desc", ["tag"], **kwargs)
    return capture["body"]


# --------------------------------------------------------------------------
# uploader_youtube: the field itself
# --------------------------------------------------------------------------

def test_synthetic_media_flag_defaults_false(monkeypatch, tmp_path):
    body = _upload(monkeypatch, tmp_path)
    assert body["status"]["containsSyntheticMedia"] is False


def test_synthetic_media_flag_can_be_set_true(monkeypatch, tmp_path):
    body = _upload(monkeypatch, tmp_path, contains_synthetic_media=True)
    assert body["status"]["containsSyntheticMedia"] is True


def test_synthetic_media_flag_is_always_present_not_only_when_true(monkeypatch, tmp_path):
    """Google's guidance is to SET the field either way, not omit it when
    false -- an explicit False is a stronger disclosure than a missing key."""
    body = _upload(monkeypatch, tmp_path, contains_synthetic_media=False)
    assert "containsSyntheticMedia" in body["status"]


# --------------------------------------------------------------------------
# backend.video_used_synthetic_media: deriving the flag from a storyboard
# --------------------------------------------------------------------------

def test_all_stock_storyboard_is_not_synthetic():
    storyboard = [{"visual_source": "stock"}, {"visual_source": "stock"}]
    assert backend.video_used_synthetic_media(storyboard) is False


def test_any_generated_scene_makes_the_whole_video_synthetic():
    storyboard = [{"visual_source": "stock"}, {"visual_source": "generate"}]
    assert backend.video_used_synthetic_media(storyboard) is True


def test_all_generated_storyboard_is_synthetic():
    storyboard = [{"visual_source": "generate"}] * 3
    assert backend.video_used_synthetic_media(storyboard) is True


def test_empty_storyboard_is_not_synthetic():
    assert backend.video_used_synthetic_media([]) is False
    assert backend.video_used_synthetic_media(None) is False


def test_untagged_legacy_scenes_default_to_synthetic():
    """Storyboards predating the visual_source field only ever used AI image
    generation, so the conservative (disclosure-favouring) default is True."""
    storyboard = [{"narration": "old generation, no visual_source key"}]
    assert backend.video_used_synthetic_media(storyboard) is True
