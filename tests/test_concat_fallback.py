"""concat_with_fallback must not propagate a stream-copy concat failure.

Reproduced live: rendering "Ancient Egyptian Princesses" failed at
`ffmpeg -f concat -c copy` with exit 183, and the real ffmpeg stderr was
thrown away by the old `stderr=subprocess.DEVNULL` call, leaving only an
opaque exit-code message in the logs.

Mismatched scene segments (stock Pexels clips, Hailuo motion clips, and Ken
Burns slideshow segments are each produced by a different code path) are the
plausible real-world trigger, but modern ffmpeg's concat demuxer is lenient
enough that codec, resolution/framerate, and audio sample-rate/channel
mismatches were all confirmed empirically to still exit 0 -- so an organic
repro is not a reliable regression test across ffmpeg versions/builds. This
test instead verifies the fallback logic directly: when the stream-copy
attempt raises, concat_with_fallback must retry with a re-encoding concat
rather than letting the failure propagate.
"""
import os

import backend


def test_concat_falls_back_to_reencode_when_stream_copy_fails(monkeypatch, tmp_path):
    calls = []

    def fake_run_ffmpeg(cmd, label=""):
        calls.append(label)
        if "stream copy" in label:
            raise RuntimeError("ffmpeg failed (exit 183): codec parameters mismatch")
        # Re-encode attempt succeeds and actually produces the output file,
        # exactly as a real re-encode would.
        with open(cmd[-1], "wb") as f:
            f.write(b"fake merged video bytes")

    monkeypatch.setattr(backend.vq, "run_ffmpeg", fake_run_ffmpeg)

    list_path = str(tmp_path / "video_list.txt")
    output_path = str(tmp_path / "merged_video.mp4")
    open(list_path, "w").close()

    backend.concat_with_fallback(list_path, output_path, "video")

    assert any("stream copy" in c for c in calls), "must attempt the fast path first"
    assert any("re-encode" in c for c in calls), "must fall back to re-encode on failure"
    assert os.path.exists(output_path), "the fallback attempt's output must survive"


def test_concat_uses_audio_reencode_args_for_wav_output(monkeypatch, tmp_path):
    """The re-encode fallback must pick codec args by output type -- pcm_s16le
    for a .wav merge, libx264 for an .mp4 merge -- not one args set for both."""
    captured_cmds = []

    def fake_run_ffmpeg(cmd, label=""):
        captured_cmds.append((cmd, label))
        if "stream copy" in label:
            raise RuntimeError("simulated stream-copy failure")
        with open(cmd[-1], "wb") as f:
            f.write(b"fake merged audio bytes")

    monkeypatch.setattr(backend.vq, "run_ffmpeg", fake_run_ffmpeg)

    list_path = str(tmp_path / "audio_list.txt")
    output_path = str(tmp_path / "merged_audio.wav")
    open(list_path, "w").close()

    backend.concat_with_fallback(list_path, output_path, "audio")

    reencode_cmd = next(cmd for cmd, label in captured_cmds if "re-encode" in label)
    assert "-c:a" in reencode_cmd and "pcm_s16le" in reencode_cmd
    assert "-c:v" not in reencode_cmd


def test_concat_stream_copy_success_never_touches_reencode(monkeypatch, tmp_path):
    """The common case: -c copy just works, no fallback should run at all."""
    calls = []

    def fake_run_ffmpeg(cmd, label=""):
        calls.append(label)
        with open(cmd[-1], "wb") as f:
            f.write(b"fake merged video bytes")

    monkeypatch.setattr(backend.vq, "run_ffmpeg", fake_run_ffmpeg)

    list_path = str(tmp_path / "video_list.txt")
    output_path = str(tmp_path / "merged_video.mp4")
    open(list_path, "w").close()

    backend.concat_with_fallback(list_path, output_path, "video")

    assert len(calls) == 1
    assert "stream copy" in calls[0]
