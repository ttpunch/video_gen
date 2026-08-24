"""Tests for the render-quality helpers.

The ffmpeg-dependent tests are the point of this file: the filter strings are
generated, and a graph that ffmpeg rejects (or silently renders as an empty
frame) is indistinguishable from a correct one until it actually runs.
"""
import json
import os
import shutil
import subprocess

import pytest

import video_quality as vq

pytestmark = pytest.mark.filterwarnings("ignore")

HAS_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


# --------------------------------------------------------------------------
# Encode arguments
# --------------------------------------------------------------------------

def test_video_encode_args_match_youtube_delivery_spec():
    args = vq.video_encode_args()
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert args[args.index("-profile:v") + 1] == "high"
    # 30 fps with a closed 2-second GOP.
    assert args[args.index("-r") + 1] == str(vq.FPS)
    assert args[args.index("-g") + 1] == str(vq.FPS * 2)
    assert args[args.index("-keyint_min") + 1] == str(vq.FPS * 2)
    # faststart is what stops playback stalling on the first frame.
    assert args[args.index("-movflags") + 1] == "+faststart"


def test_quality_presets_order_crf_from_worst_to_best():
    crfs = [vq.QUALITY_PRESETS[name]["crf"] for name in
            ("Draft (fast)", "Standard", "High (recommended)", "Maximum")]
    assert crfs == sorted(crfs, reverse=True)
    assert vq.DEFAULT_QUALITY in vq.QUALITY_PRESETS


def test_intermediate_args_skip_faststart_but_stay_near_transparent():
    args = vq.intermediate_encode_args()
    assert "-movflags" not in args
    assert int(args[args.index("-crf") + 1]) <= 18


def test_audio_encode_args_are_48khz_stereo_aac():
    args = vq.audio_encode_args()
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-ar") + 1] == "48000"
    assert args[args.index("-ac") + 1] == "2"


# --------------------------------------------------------------------------
# Ken Burns
# --------------------------------------------------------------------------

def test_ken_burns_cycles_through_distinct_moves():
    """Consecutive scenes must not all push in the same direction."""
    chains = {vq.ken_burns_vf(i, 3.0) for i in range(len(vq._MOVES))}
    assert len(chains) == len(vq._MOVES)


def test_ken_burns_supersamples_before_zooming():
    """Zooming a 1080-wide still directly is what produced the stair-stepping."""
    chain = vq.ken_burns_vf(0, 3.0)
    assert f"scale={vq.SHORT_W * vq.SUPERSAMPLE}:{vq.SHORT_H * vq.SUPERSAMPLE}" in chain
    assert chain.index("scale=") < chain.index("zoompan=")


def test_ken_burns_zoom_spans_the_whole_scene_regardless_of_length():
    """The old `zoom+0.001` accumulator under-moved short scenes and froze long ones."""
    for duration in (1.0, 4.0, 12.0):
        chain = vq.ken_burns_vf(0, duration)
        frames = int(round(duration * vq.FPS))
        assert f"d={frames}" in chain
        assert f"(on/{frames})" in chain


def test_hook_scene_pushes_harder_than_a_body_scene():
    hook = vq.ken_burns_vf(0, 3.0, is_hook=True)
    body = vq.ken_burns_vf(0, 3.0, is_hook=False)
    assert "0.2600" in hook and "0.1600" in body


def test_motion_off_produces_no_zoompan():
    assert "zoompan" not in vq.ken_burns_vf(0, 3.0, motion_style="Off")


@needs_ffmpeg
@pytest.mark.parametrize("index", range(6))
def test_every_ken_burns_move_renders(index, tmp_path):
    still = tmp_path / "still.png"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:d=1:r=1",
         "-frames:v", "1", str(still)],
        check=True, capture_output=True)

    out = tmp_path / f"kb{index}.mp4"
    vq.run_ffmpeg(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(still), "-t", "1",
         "-vf", vq.ken_burns_vf(index, 1.0)]
        + vq.intermediate_encode_args() + [str(out)],
        label="ken burns")

    info = vq.probe(str(out))
    assert (info["width"], info["height"]) == (vq.SHORT_W, vq.SHORT_H)
    assert info["fps"] == float(vq.FPS)


# --------------------------------------------------------------------------
# Audio mixing
# --------------------------------------------------------------------------

def test_music_mix_disables_amix_normalization():
    """amix normalizes by default, which halved the narration level."""
    assert "normalize=0" in vq.music_mix_filter(duck=True)
    assert "normalize=0" in vq.music_mix_filter(duck=False)


def test_ducking_uses_the_voice_as_sidechain_key():
    graph = vq.music_mix_filter(duck=True)
    assert "sidechaincompress" in graph
    assert graph.endswith("[aout]")


@needs_ffmpeg
def test_ducked_mix_renders_and_keeps_voice_present(tmp_path):
    voice, music, mixed = (str(tmp_path / n) for n in ("v.wav", "m.wav", "mix.wav"))
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:d=3",
                    "-c:a", "pcm_s16le", voice], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:a=0.4",
                    "-c:a", "pcm_s16le", music], check=True, capture_output=True)

    vq.run_ffmpeg(["ffmpeg", "-y", "-i", voice, "-i", music,
                   "-filter_complex", vq.music_mix_filter(),
                   "-map", "[aout]", "-c:a", "pcm_s16le", mixed], label="mix")
    assert os.path.getsize(mixed) > 0


@needs_ffmpeg
def test_normalize_loudness_hits_the_youtube_target(tmp_path):
    quiet, loud = str(tmp_path / "quiet.wav"), str(tmp_path / "loud.wav")
    # ~-30 LUFS: a plausibly quiet narration mix. Anything far below that needs
    # more than MAX_GAIN_DB and is deliberately left short of the target.
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:d=4",
                    "-af", "volume=0.15", "-c:a", "pcm_s16le", quiet],
                   check=True, capture_output=True)

    vq.normalize_loudness(quiet, loud, log=lambda *_: None)
    measured = vq.measure_loudness(loud)
    assert measured is not None
    # loudnorm lands within a fraction of a LU of the target.
    assert abs(float(measured["input_i"]) - vq.TARGET_LUFS) < 1.0
    assert float(measured["input_tp"]) <= vq.TARGET_TRUE_PEAK + 0.5


def test_normalize_loudness_falls_back_instead_of_raising(tmp_path, monkeypatch):
    """A broken audio file must not take the whole render down with it."""
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    src.write_bytes(b"not audio")
    monkeypatch.setattr(vq, "measure_loudness", lambda *a, **k: None)
    vq.normalize_loudness(str(src), str(dst), log=lambda *_: None)
    assert dst.exists()


def test_gain_filter_never_uses_loudnorm():
    """loudnorm silently goes DYNAMIC when source LRA exceeds target LRA, which
    rode a real render up by +13.5 LU from start to finish."""
    measured = {"input_i": "-25.9", "input_tp": "-7.4", "input_lra": "15.2",
                "input_thresh": "-36.9", "target_offset": "-1.5"}
    chain = vq.gain_filter(measured)
    assert "loudnorm" not in chain
    assert chain.startswith("volume=")


def test_gain_moves_the_mix_to_the_target():
    measured = {"input_i": "-25.9", "input_tp": "-40.0", "input_lra": "5.0",
                "input_thresh": "-36.9", "target_offset": "0"}
    # -25.9 -> -14.0 needs +11.9 dB, and there is ample true-peak headroom.
    assert "volume=11.90dB" in vq.gain_filter(measured)


def test_loud_transients_do_not_hold_the_whole_mix_down():
    """A single whoosh peak used to cap the gain, losing ~5 LU of loudness.

    YouTube lowers loud uploads but never raises quiet ones, so that loudness is
    simply lost. The limiter shaves the transient instead.
    """
    measured = {"input_i": "-25.9", "input_tp": "-3.0", "input_lra": "5.0",
                "input_thresh": "-36.9", "target_offset": "0"}
    chain = vq.gain_filter(measured)
    assert "volume=11.90dB" in chain, "gain was capped by the peak again"
    assert "alimiter" in chain, "no limiter to catch the transient"


def test_gain_is_bounded_so_silence_is_not_amplified_into_noise():
    measured = {"input_i": "-90.0", "input_tp": "-90.0", "input_lra": "1.0",
                "input_thresh": "-99.0", "target_offset": "0"}
    assert f"volume={vq.MAX_GAIN_DB:.2f}dB" in vq.gain_filter(measured)


def test_limiter_ceiling_matches_the_true_peak_target():
    measured = {"input_i": "-25.9", "input_tp": "-3.0", "input_lra": "5.0",
                "input_thresh": "-36.9", "target_offset": "0"}
    expected = 10 ** (vq.TARGET_TRUE_PEAK / 20.0)
    assert f"limit={expected:.4f}" in vq.gain_filter(measured)


def test_no_measurements_means_no_level_change():
    """Better a quiet video than one that ramps."""
    assert vq.gain_filter(None) == "anull"
    assert vq.gain_filter({"input_i": "oops"}) == "anull"


@needs_ffmpeg
def test_normalized_audio_does_not_drift_over_time(tmp_path):
    """The regression that shipped: level crept upward as the video played.

    A wide-dynamic-range source (loud speech, near-silent gaps) is exactly what
    pushed loudnorm into dynamic mode, so that is what is rendered here.
    """
    src, dst = str(tmp_path / "wide.wav"), str(tmp_path / "flat.wav")
    # Quiet first half, loud second half -> large LRA, like narration with gaps.
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:d=20",
         "-af", "volume='if(lt(t,10),0.05,0.5)':eval=frame",
         "-c:a", "pcm_s16le", src],
        check=True, capture_output=True)

    vq.normalize_loudness(src, dst, log=lambda *_: None)

    proc = subprocess.run(
        ["ffmpeg", "-nostats", "-i", dst, "-filter_complex", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True)
    short_term = []
    for line in proc.stderr.splitlines():
        if "S:" in line and "t:" in line:
            parts = line.split()
            try:
                short_term.append(float(parts[parts.index("S:") + 1]))
            except (ValueError, IndexError):
                pass

    loud = [s for s in short_term if s > -70]
    assert len(loud) > 6, "not enough loudness samples"
    # Compare like with like: the second half of the (already loud) tail must not
    # be materially louder than the first part of it.
    tail = loud[len(loud) // 2:]
    early, late = tail[: len(tail) // 2], tail[len(tail) // 2:]
    drift = sum(late) / len(late) - sum(early) / len(early)
    assert abs(drift) < 2.0, f"level drifted {drift:+.1f} LU across the tail"


# --------------------------------------------------------------------------
# Overlays and text escaping
# --------------------------------------------------------------------------

def test_sanitize_inline_text_drops_quote_and_colon():
    """Neither can be escaped inside a filter-graph option value."""
    cleaned = vq.sanitize_inline_text("@my'chan:nel")
    assert "'" not in cleaned and ":" not in cleaned


def test_build_finish_filter_chains_every_burn_in_into_one_pass():
    chain = vq.build_finish_filter(
        subtitles_path="temp/subs.ass", total_duration=15.0,
        subscribe=True, channel_handle="@chan", progress_bar=True)
    assert "subtitles=" in chain
    assert "drawbox=" in chain          # progress bar
    assert "SUBSCRIBE" in chain
    assert chain.count("subtitles=") == 1


def test_build_finish_filter_returns_none_when_nothing_to_burn():
    assert vq.build_finish_filter(total_duration=10.0) is None


def _bar_fill_fraction(video, at, width, height, bar_h=10):
    """Fraction of the bottom bar row that is lit, measured from real pixels."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1",
         "-vf", f"crop={width}:2:0:{height - bar_h + 2}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True).stdout
    assert raw, f"no pixels sampled at t={at}"
    return sum(1 for px in raw if px > 150) / len(raw)


@needs_ffmpeg
def test_progress_bar_actually_advances_with_playback(tmp_path):
    """The obvious drawbox form resolves its width once and renders full immediately.

    Asserting on the filter string cannot catch that -- only real pixels can.
    """
    duration, width, height = 10.0, 400, 200
    out = str(tmp_path / "bar.mp4")
    vq.run_ffmpeg(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=black:s={width}x{height}:d={duration}:r=30",
         "-vf", vq.progress_bar_filter(duration)]
        + vq.video_encode_args("Draft (fast)") + [out],
        label="progress bar")

    for expected in (0.1, 0.5, 0.9):
        got = _bar_fill_fraction(out, duration * expected, width, height)
        assert abs(got - expected) < 0.1, (
            f"at {expected:.0%} through, bar was {got:.0%} full")


@needs_ffmpeg
def test_progress_bar_composes_with_the_other_burn_ins(tmp_path):
    """The bar's graph uses named pads, so it must survive being chained."""
    duration, width, height = 6.0, 1080, 1920
    out = str(tmp_path / "combined.mp4")
    chain = vq.build_finish_filter(
        total_duration=duration, subscribe=True,
        channel_handle="@chan", progress_bar=True)
    vq.run_ffmpeg(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=black:s={width}x{height}:d={duration}:r=30",
         "-vf", chain] + vq.video_encode_args("Draft (fast)") + [out],
        label="combined burn-in")

    early = _bar_fill_fraction(out, duration * 0.15, width, height)
    late = _bar_fill_fraction(out, duration * 0.85, width, height)
    assert early < 0.3 < late, f"bar did not advance ({early:.0%} -> {late:.0%})"


@needs_ffmpeg
@pytest.mark.parametrize("title", [
    "What's really inside a black hole",
    "50% of people don't know this: why?",
    "The AI that taught itself [BANNED] tricks!",
    "Comma, colon: quote' and 100% together",
])
def test_thumbnail_renders_for_titles_with_hostile_punctuation(title, tmp_path):
    """Apostrophes and '%' both used to blank the overlay while exiting 0."""
    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:d=1:r=30",
         "-frames:v", "20", "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True)

    out = tmp_path / "thumb.jpg"
    result = vq.generate_thumbnail(str(src), title, str(out), log=lambda *_: None)
    assert result is not None, f"thumbnail failed for {title!r}"
    # A blank 1080x1920 JPEG compresses to a few KB; a real frame with burnt-in
    # text does not. This is what catches the silent empty-overlay failure.
    assert out.stat().st_size > 20_000


@needs_ffmpeg
def test_finish_filter_renders_as_a_single_encode(tmp_path):
    src, out = tmp_path / "src.mp4", tmp_path / "out.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:d=2:r=30",
         "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True)

    chain = vq.build_finish_filter(total_duration=2.0, subscribe=True,
                                   channel_handle="@channel", progress_bar=True)
    vq.run_ffmpeg(["ffmpeg", "-y", "-i", str(src), "-vf", chain]
                  + vq.video_encode_args() + ["-an", str(out)], label="finish")
    info = vq.probe(str(out))
    assert (info["width"], info["height"]) == (vq.SHORT_W, vq.SHORT_H)


# --------------------------------------------------------------------------
# Error surfacing
# --------------------------------------------------------------------------

@needs_ffmpeg
def test_run_ffmpeg_includes_stderr_in_the_error(tmp_path):
    with pytest.raises(RuntimeError) as excinfo:
        vq.run_ffmpeg(["ffmpeg", "-y", "-i", str(tmp_path / "missing.mp4"),
                       str(tmp_path / "out.mp4")], label="probe")
    # The old DEVNULL behaviour left callers with only an exit code.
    assert "probe failed" in str(excinfo.value)
    assert len(str(excinfo.value)) > 40


def test_probe_returns_empty_dict_for_a_missing_file(tmp_path):
    assert vq.probe(str(tmp_path / "nope.mp4")) == {}
