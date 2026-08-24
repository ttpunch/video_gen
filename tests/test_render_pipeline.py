"""End-to-end render test for the viral shorts pipeline.

Image generation, TTS and the LLM are the slow, network-bound parts; the ffmpeg
chain underneath them is where the output quality is actually decided. Feeding
the pipeline a storyboard whose assets already exist exercises that whole chain
for real -- Ken Burns, concat, ducking, loudness, burn-in and thumbnail -- and
asserts the delivered file matches the YouTube spec.
"""
import os
import shutil
import subprocess

import pytest

import video_quality as vq

HAS_FFMPEG = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


@pytest.fixture
def storyboard(tmp_path):
    """Three scenes with real image + audio files already on disk."""
    scenes = []
    for i in range(3):
        img = tmp_path / f"scene{i}.png"
        aud = tmp_path / f"scene{i}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"testsrc2=size=1080x1920:d=1:r=1,hue=h={i * 60}",
             "-frames:v", "1", str(img)],
            check=True, capture_output=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"sine=frequency={220 + i * 60}:d=1.5",
             "-ar", "24000", "-c:a", "pcm_s16le", str(aud)],
            check=True, capture_output=True)
        scenes.append({
            "speaker": "Sarah (Female - US - Soft)",
            "narration": f"Scene {i + 1} narration line, it's 50% done: really.",
            "visual_prompt": f"scene {i + 1}",
            "image_path": str(img),
            "audio_path": str(aud),
        })
    return scenes


@pytest.fixture
def render(storyboard, monkeypatch, tmp_path):
    """Run the pipeline with its outputs redirected into a temp workspace."""
    import backend

    # Keep temp/ and outputs/ writes inside the test's own directory.
    workdir = tmp_path / "work"
    (workdir / "temp").mkdir(parents=True)
    (workdir / "outputs").mkdir(parents=True)
    monkeypatch.chdir(workdir)

    def run(**overrides):
        kwargs = dict(
            prompt="test topic",
            model="unused",
            custom_storyboard=storyboard,
            music_style="None",
            satisfying_background="None",
            enable_captions=False,
            caption_sync=False,
            enable_transition_sfx=False,
            subscribe_overlay=False,
            progress_bar=False,
            enable_thumbnail=False,
            quality="Draft (fast)",
            log_callback=lambda *_: None,
        )
        kwargs.update(overrides)
        return backend.run_viral_shorts_pipeline_new(**kwargs)

    return run


def test_rendered_short_matches_youtube_delivery_spec(render):
    video, storyboard, _topic, _script = render()

    assert os.path.exists(video)
    info = vq.probe(video)
    assert (info["width"], info["height"]) == (1080, 1920), "must be vertical 1080p"
    assert info["fps"] == 30.0, "25 fps forces a resample on YouTube's ladder"
    assert info["video_codec"] == "h264"
    assert info["audio_codec"] == "aac"
    assert info["sample_rate"] == 48000
    assert len(storyboard) == 3


def test_rendered_short_starts_without_buffering(render):
    """faststart moves the moov atom to the front so playback begins instantly."""
    video, *_ = render()
    with open(video, "rb") as handle:
        head = handle.read(65536)
    assert b"moov" in head, "moov atom is not at the front of the file"
    assert head.index(b"moov") < head.index(b"mdat") if b"mdat" in head else True


def test_narration_is_delivered_at_the_youtube_loudness_target(render):
    video, *_ = render(normalize_audio=True)
    measured = vq.measure_loudness(video)
    assert measured is not None
    assert abs(float(measured["input_i"]) - vq.TARGET_LUFS) < 1.5
    assert float(measured["input_tp"]) <= vq.TARGET_TRUE_PEAK + 0.5


def test_skipping_normalization_leaves_the_mix_quiet(render):
    """Guards against the flag silently doing nothing."""
    video, *_ = render(normalize_audio=False)
    measured = vq.measure_loudness(video)
    assert measured is not None
    assert float(measured["input_i"]) < vq.TARGET_LUFS - 1.0


def test_burn_in_overlays_render_in_a_single_pass(render):
    video, *_ = render(subscribe_overlay=True, progress_bar=True,
                       channel_handle="@testchannel")
    info = vq.probe(video)
    assert (info["width"], info["height"]) == (1080, 1920)
    # One output file, not the old _sub.mp4 second-generation copy.
    assert not video.endswith("_sub.mp4")
    assert os.path.exists(video)


def test_thumbnail_is_written_next_to_the_video(render):
    video, _sb, _topic, script_data = render(enable_thumbnail=True)
    thumb = script_data.get("thumbnail_path")
    assert thumb and os.path.exists(thumb)
    assert os.path.getsize(thumb) > 20_000, "thumbnail looks blank"


def test_motion_style_off_still_produces_a_valid_video(render):
    video, *_ = render(motion_style="Off")
    info = vq.probe(video)
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["fps"] == 30.0


def test_scene_durations_survive_into_the_final_file(render):
    video, storyboard, *_ = render()
    expected = sum(s["duration"] for s in storyboard)
    actual = vq.probe(video)["duration"]
    assert abs(actual - expected) < 0.5, f"expected ~{expected:.2f}s, got {actual:.2f}s"
