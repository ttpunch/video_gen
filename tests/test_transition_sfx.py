"""Transition whooshes must not alter the narration's level or ride it upward.

Two amix defaults conspired here: `normalize` divided the mix by the input
count (dropping narration ~13 dB), and `dropout_transition` ramped the gain up
over 2s every time a whoosh ended -- a staircase of rises across the video that
users hear as "the volume keeps increasing".
"""
import shutil
import subprocess

import pytest

import backend

HAS_FFMPEG = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


def _loudness(path):
    """(integrated LUFS, list of short-term LUFS) for a file."""
    proc = subprocess.run(
        ["ffmpeg", "-nostats", "-i", path, "-filter_complex", "ebur128",
         "-f", "null", "-"],
        capture_output=True, text=True)
    short = []
    integrated = None
    for line in proc.stderr.splitlines():
        if "S:" in line and "t:" in line:
            parts = line.split()
            try:
                short.append(float(parts[parts.index("S:") + 1]))
            except (ValueError, IndexError):
                pass
        if "I:" in line and "LUFS" in line:
            parts = line.split()
            try:
                integrated = float(parts[parts.index("I:") + 1])
            except (ValueError, IndexError):
                pass
    return integrated, [s for s in short if s > -70]


@pytest.fixture
def speech_like(tmp_path):
    """20s of steady tone standing in for narration: any drift is the mixer's."""
    path = str(tmp_path / "voice.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:d=20",
         "-af", "volume=0.3", "-c:a", "pcm_s16le", path],
        check=True, capture_output=True)
    return path


@pytest.fixture
def whoosh(tmp_path, monkeypatch):
    """Put a short whoosh where mix_transition_sfx looks for one."""
    sfx_dir = tmp_path / "assets" / "sfx"
    sfx_dir.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.4:c=white:a=0.5",
         "-c:a", "pcm_s16le", str(sfx_dir / "whoosh.wav")],
        check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    return str(sfx_dir / "whoosh.wav")


def _loudness_of_window(path, start, duration, tmp_path, tag):
    """Integrated loudness of one slice, so added SFX elsewhere cannot skew it."""
    clip = str(tmp_path / f"win_{tag}.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", path,
         "-c:a", "pcm_s16le", clip],
        check=True, capture_output=True)
    return _loudness(clip)[0]


def test_sfx_does_not_attenuate_the_narration(speech_like, whoosh, tmp_path):
    """amix's default normalization divided the whole mix by the input count.

    Measured in a window containing NO whoosh -- comparing whole-file loudness
    would just show the energy the whooshes themselves add, which is expected.
    """
    out = str(tmp_path / "mixed.wav")
    backend.mix_transition_sfx(speech_like, out, [4.0, 8.0, 12.0, 16.0])

    # 5.5s-7.5s sits between the whooshes at 4s and 8s (each 0.4s long).
    before = _loudness_of_window(speech_like, 5.5, 2.0, tmp_path, "before")
    after = _loudness_of_window(out, 5.5, 2.0, tmp_path, "after")
    assert before is not None and after is not None
    assert abs(after - before) < 1.0, \
        f"narration level moved {after - before:+.1f} LU between whooshes"


def test_sfx_does_not_ramp_the_level_over_time(speech_like, whoosh, tmp_path):
    """amix's dropout_transition raised the gain each time a whoosh ended."""
    out = str(tmp_path / "mixed.wav")
    backend.mix_transition_sfx(speech_like, out, [4.0, 8.0, 12.0, 16.0])
    _integrated, short = _loudness(out)
    assert len(short) > 8
    first, last = short[: len(short) // 3], short[-len(short) // 3:]
    drift = sum(last) / len(last) - sum(first) / len(first)
    assert abs(drift) < 1.5, f"level drifted {drift:+.1f} LU across the video"


def test_more_transitions_do_not_mean_quieter_audio(speech_like, whoosh, tmp_path):
    """The attenuation scaled with input count, so a 7-scene reel suffered most.

    Sampled at 17-19s, past every whoosh in both arrangements.
    """
    levels = []
    for count in (1, 6):
        out = str(tmp_path / f"mix{count}.wav")
        backend.mix_transition_sfx(speech_like, out,
                                   [2.0 * (i + 1) for i in range(count)])
        levels.append(_loudness_of_window(out, 17.0, 2.0, tmp_path, f"n{count}"))
    assert abs(levels[1] - levels[0]) < 1.0, \
        f"6 transitions was {levels[1] - levels[0]:+.1f} LU vs 1 transition"


def test_missing_whoosh_passes_audio_through_untouched(speech_like, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # no assets/sfx/whoosh.wav here
    out = str(tmp_path / "copy.wav")
    backend.mix_transition_sfx(speech_like, out, [2.0])
    assert _loudness(out)[0] == pytest.approx(_loudness(speech_like)[0], abs=0.2)


def test_no_transitions_passes_audio_through(speech_like, whoosh, tmp_path):
    out = str(tmp_path / "copy.wav")
    backend.mix_transition_sfx(speech_like, out, [])
    assert _loudness(out)[0] == pytest.approx(_loudness(speech_like)[0], abs=0.2)
