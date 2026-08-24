"""Real stock footage in the shorts pipeline.

Generated people come out with distorted hands and duplicated objects; filmed
people do not. These tests cover the source-selection logic and then run the
REAL ffmpeg chain on a synthetic clip, so a broken filter graph or a
resolution/fps mismatch at concat time fails here rather than in a render.

Pexels itself is never called — the network boundary is monkeypatched.
"""
import os
import shutil
import subprocess

import pytest

import backend
import stock_footage
import video_quality as vq

HAS_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


# --------------------------------------------------------------------------
# Which source does a scene get?
# --------------------------------------------------------------------------

def test_smart_mix_honours_the_storyboard_tag():
    assert backend.use_stock_for_scene({"visual_source": "stock"}, "Smart Mix") is True
    assert backend.use_stock_for_scene({"visual_source": "generate"}, "Smart Mix") is False


def test_unfilmable_shots_are_generated_not_searched():
    """'Inside a black hole' has no stock clip; forcing one would look wrong."""
    scene = {"visual_source": "generate", "stock_query": "black hole interior"}
    assert backend.use_stock_for_scene(scene, "Smart Mix") is False


@pytest.mark.parametrize("mode,expected", [
    ("Real Footage Only", True),
    ("AI Only", False),
])
def test_explicit_modes_override_the_tag(mode, expected):
    for tag in ("stock", "generate", None):
        scene = {"visual_source": tag} if tag else {}
        assert backend.use_stock_for_scene(scene, mode) is expected


def test_untagged_legacy_scenes_keep_generating():
    """Storyboards saved before this feature must not silently change behaviour."""
    assert backend.use_stock_for_scene({"visual_prompt": "a cat"}, "Smart Mix") is False
    # ...unless they carry an explicit query.
    assert backend.use_stock_for_scene({"stock_query": "a cat"}, "Smart Mix") is True


# --------------------------------------------------------------------------
# The Pexels client
# --------------------------------------------------------------------------

def _fake_response(videos, status=200):
    class R:
        status_code = status
        text = ""

        @staticmethod
        def json():
            return {"videos": videos}
    return R()


def test_largest_clip_meeting_the_size_floor_wins(monkeypatch):
    """Downscaling is lossless-ish; upscaling is not. Prefer the bigger file."""
    videos = [{"video_files": [
        {"file_type": "video/mp4", "height": 960, "link": "small"},
        {"file_type": "video/mp4", "height": 1920, "link": "hd"},
        {"file_type": "video/mp4", "height": 3840, "link": "uhd"},
    ]}]
    monkeypatch.setattr(stock_footage.requests, "get", lambda *a, **k: _fake_response(videos))
    got = stock_footage.search_pexels_video("x", "key", min_height=1920, log=lambda *_: None)
    assert got == "uhd"


def test_clips_below_the_size_floor_are_rejected(monkeypatch):
    videos = [{"video_files": [{"file_type": "video/mp4", "height": 720, "link": "small"}]}]
    monkeypatch.setattr(stock_footage.requests, "get", lambda *a, **k: _fake_response(videos))
    assert stock_footage.search_pexels_video("x", "key", min_height=1920,
                                             log=lambda *_: None) is None


def test_query_widens_until_something_matches(monkeypatch):
    """A cinematic visual_prompt gets no stock hits, so the query must broaden."""
    tried = []

    def fake_candidates(query, key, orientation, min_height=0, per_page=20, log=None):
        tried.append(query)
        # (video_id, url, height)
        return [(1, "url", 1920)] if query == "abstract background" else []

    monkeypatch.setattr(stock_footage, "search_pexels_candidates", fake_candidates)
    monkeypatch.setattr(stock_footage, "download_video_file", lambda *a, **k: True)

    out = stock_footage.fetch_clip("a lone silhouetted figure at dusk", "/tmp/x.mp4",
                                   api_key="key", global_focus="a diver",
                                   log=lambda *_: None)
    assert out == "/tmp/x.mp4"
    assert "abstract background" in tried
    assert len(tried) > 1, "should have tried narrower queries first"


def test_missing_api_key_returns_none_rather_than_raising(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert stock_footage.search_pexels_video("x", "", log=lambda *_: None) is None


# --------------------------------------------------------------------------
# End-to-end render
# --------------------------------------------------------------------------

@pytest.fixture
def render(tmp_path, monkeypatch):
    """Pipeline with Pexels stubbed by a locally generated clip."""
    workdir = tmp_path / "work"
    (workdir / "temp").mkdir(parents=True)
    (workdir / "outputs").mkdir(parents=True)

    # A 2s 4K-vertical clip standing in for whatever Pexels would return.
    stock_src = tmp_path / "stock.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:d=2:r=30",
         "-pix_fmt", "yuv420p", str(stock_src)],
        check=True, capture_output=True)

    fetched = []

    def fake_fetch(query, dest, **kwargs):
        fetched.append(query)
        shutil.copy(stock_src, dest)
        return dest

    monkeypatch.setattr(backend.stock_footage, "fetch_clip", fake_fetch)
    monkeypatch.chdir(workdir)

    def build_scene(i, source):
        img = tmp_path / f"img{i}.png"
        aud = tmp_path / f"aud{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"testsrc2=size=1080x1920:d=1:r=1", "-frames:v", "1", str(img)],
                       check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:d=1.5",
                        "-ar", "24000", "-c:a", "pcm_s16le", str(aud)],
                       check=True, capture_output=True)
        return {
            "speaker": "Sarah (Female - US - Soft)",
            "narration": f"Scene {i + 1}.",
            "visual_prompt": f"scene {i + 1}",
            "visual_source": source,
            "stock_query": f"query {i + 1}",
            "image_path": str(img),
            "audio_path": str(aud),
        }

    def run(sources=("stock", "generate"), **overrides):
        kwargs = dict(
            prompt="test", model="unused",
            custom_storyboard=[build_scene(i, s) for i, s in enumerate(sources)],
            music_style="None", enable_captions=False, caption_sync=False,
            enable_transition_sfx=False, subscribe_overlay=False,
            progress_bar=False, enable_thumbnail=False, quality="Draft (fast)",
            log_callback=lambda *_: None,
        )
        kwargs.update(overrides)
        return backend.run_viral_shorts_pipeline_new(**kwargs), fetched

    return run


@needs_ffmpeg
def test_stock_scene_renders_to_delivery_spec(render):
    (video, storyboard, _t, _s), fetched = render(sources=("stock",))
    info = vq.probe(video)
    assert (info["width"], info["height"]) == (vq.SHORT_W, vq.SHORT_H)
    assert info["fps"] == float(vq.FPS)
    assert storyboard[0]["visual_source"] == "stock"
    assert fetched, "Pexels was never queried for a stock-tagged scene"


@needs_ffmpeg
def test_mixed_stock_and_generated_scenes_concat_cleanly(render):
    """Different sources must not produce a resolution or fps mismatch."""
    (video, storyboard, _t, _s), _ = render(sources=("stock", "generate", "stock"))
    info = vq.probe(video)
    assert (info["width"], info["height"]) == (vq.SHORT_W, vq.SHORT_H)
    assert [s["visual_source"] for s in storyboard] == ["stock", "generated", "stock"]


@needs_ffmpeg
def test_clip_is_fitted_to_the_narration_length(render):
    """A 2s stock clip must loop or trim to match the scene's audio."""
    (video, storyboard, _t, _s), _ = render(sources=("stock", "stock"))
    expected = sum(s["duration"] for s in storyboard)
    assert abs(vq.probe(video)["duration"] - expected) < 0.5


@needs_ffmpeg
def test_pexels_miss_falls_back_to_generation(render, monkeypatch):
    """A stock miss must never fail the render."""
    monkeypatch.setattr(backend.stock_footage, "fetch_clip", lambda *a, **k: None)
    (video, storyboard, _t, _s), _ = render(sources=("stock",))
    assert os.path.exists(video)
    assert storyboard[0]["visual_source"] == "generated"


@needs_ffmpeg
def test_ai_only_mode_never_calls_pexels(render):
    (_result, storyboard, _t, _s), fetched = render(
        sources=("stock", "stock"), visual_source_mode="AI Only")
    assert fetched == []
    assert all(s["visual_source"] == "generated" for s in storyboard)


@needs_ffmpeg
def test_real_footage_only_mode_uses_stock_everywhere(render):
    (_result, storyboard, _t, _s), fetched = render(
        sources=("generate", "generate"), visual_source_mode="Real Footage Only")
    assert len(fetched) == 2
    assert all(s["visual_source"] == "stock" for s in storyboard)


@needs_ffmpeg
def test_existing_clip_is_reused_on_resume(render, monkeypatch, tmp_path):
    """Re-running a partially-failed render must not re-download."""
    existing = tmp_path / "already.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1080x1920:d=2:r=30", "-pix_fmt", "yuv420p",
                    str(existing)], check=True, capture_output=True)

    calls = []
    monkeypatch.setattr(backend.stock_footage, "fetch_clip",
                        lambda *a, **k: calls.append(1))

    img, aud = tmp_path / "i.png", tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:d=1:r=1",
                    "-frames:v", "1", str(img)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:d=1",
                    "-ar", "24000", "-c:a", "pcm_s16le", str(aud)],
                   check=True, capture_output=True)

    render(sources=(), custom_storyboard=[{
        "speaker": "Sarah (Female - US - Soft)", "narration": "hi",
        "visual_prompt": "x", "visual_source": "stock",
        "clip_path": str(existing), "image_path": str(img), "audio_path": str(aud),
    }])
    assert calls == [], "resume re-downloaded an existing clip"


def test_stock_grade_is_a_chainable_fragment():
    """It is appended inside an existing -vf chain, so it needs a leading comma."""
    grade = vq.stock_grade()
    assert grade.startswith(",")
    assert "eq=" in grade


# --------------------------------------------------------------------------
# Clip de-duplication and variety
# --------------------------------------------------------------------------
#
# Measured against the live Pexels API before this existed: picking only the
# largest match made selection deterministic, so (a) two scenes with
# overlapping queries could land on the same clip, (b) every scene that fell
# through to the generic "abstract background" backdrop got the *identical*
# clip, and (c) re-rendering the same topic returned byte-identical footage.
# For a channel posting repeatedly around one subject that reads as recycled
# stock.

def _pool(n=5, height=1920):
    """A fake candidate pool: n distinct videos, all the same resolution."""
    return [(i, f"url{i}", height) for i in range(n)]


def test_same_clip_is_never_used_twice_in_one_video(monkeypatch):
    monkeypatch.setattr(stock_footage, "search_pexels_candidates",
                        lambda *a, **k: _pool(5))
    monkeypatch.setattr(stock_footage, "download_video_file", lambda *a, **k: True)

    used = set()
    for _ in range(4):
        stock_footage.fetch_clip("deep ocean", "/tmp/x.mp4", api_key="k",
                                 used_ids=used, log=lambda *_: None)
    assert len(used) == 4, "each scene must claim a distinct clip"


def test_generic_fallback_does_not_repeat_across_scenes(monkeypatch):
    """The backdrop fallback resolved to one identical clip for every scene."""
    monkeypatch.setattr(stock_footage, "search_pexels_candidates",
                        lambda query, *a, **k: _pool(6) if query == "abstract background" else [])
    monkeypatch.setattr(stock_footage, "download_video_file", lambda *a, **k: True)

    # A fixed seed makes selection deterministic, so WITHOUT de-duplication all
    # three scenes would resolve to the identical clip -- which is precisely the
    # bug. Passing the same seed each call proves de-dup is what separates them,
    # rather than luck in the random draw.
    used = set()
    for _ in range(3):
        stock_footage.fetch_clip("something unfilmable", "/tmp/x.mp4", api_key="k",
                                 used_ids=used, variety_seed=7,
                                 log=lambda *_: None)
    assert len(used) == 3, "three scenes fell back and must still differ"


def test_exhausted_pool_widens_instead_of_repeating(monkeypatch):
    """When every match is taken, widen the query rather than reuse a clip."""
    queries = []

    def fake(query, *a, **k):
        queries.append(query)
        # Narrow query has one clip; the broad backdrop has plenty.
        return _pool(1) if query != "abstract background" else _pool(5)

    monkeypatch.setattr(stock_footage, "search_pexels_candidates", fake)
    monkeypatch.setattr(stock_footage, "download_video_file", lambda *a, **k: True)

    used = {0}  # the narrow query's only clip is already used
    out = stock_footage.fetch_clip("deep ocean water", "/tmp/x.mp4", api_key="k",
                                   used_ids=used, log=lambda *_: None)
    assert out == "/tmp/x.mp4"
    assert "abstract background" in queries, "should widen when the pool is exhausted"


def test_variety_seed_is_reproducible(monkeypatch):
    monkeypatch.setattr(stock_footage, "search_pexels_candidates",
                        lambda *a, **k: _pool(10))
    monkeypatch.setattr(stock_footage, "download_video_file", lambda *a, **k: True)

    def pick(seed):
        used = set()
        stock_footage.fetch_clip("q", "/tmp/x.mp4", api_key="k", used_ids=used,
                                 variety_seed=seed, log=lambda *_: None)
        return used.pop()

    assert pick(42) == pick(42), "same seed must reproduce the same footage"


def test_different_seeds_pick_different_footage(monkeypatch):
    """Two videos on the same topic should not recycle identical clips."""
    monkeypatch.setattr(stock_footage, "search_pexels_candidates",
                        lambda *a, **k: _pool(10))
    monkeypatch.setattr(stock_footage, "download_video_file", lambda *a, **k: True)

    def pick(seed):
        used = set()
        stock_footage.fetch_clip("q", "/tmp/x.mp4", api_key="k", used_ids=used,
                                 variety_seed=seed, log=lambda *_: None)
        return used.pop()

    picks = {pick(s) for s in range(12)}
    assert len(picks) > 1, "seeding produced identical footage for every video"


def test_candidates_are_one_entry_per_video_not_per_encode(monkeypatch):
    """A pool of 5 renditions of ONE clip is not 5 choices."""
    payload = {"videos": [
        {"id": 7, "video_files": [
            {"file_type": "video/mp4", "height": 1920, "link": "a"},
            {"file_type": "video/mp4", "height": 3840, "link": "b"},
            {"file_type": "video/mp4", "height": 2160, "link": "c"},
        ]},
    ]}

    class R:
        status_code = 200
        text = ""
        @staticmethod
        def json():
            return payload

    monkeypatch.setattr(stock_footage.requests, "get", lambda *a, **k: R())
    cands = stock_footage.search_pexels_candidates("q", "key", log=lambda *_: None)
    assert len(cands) == 1, "one video must yield one candidate"
    assert cands[0][2] == 3840, "and it should carry that video's largest rendition"
