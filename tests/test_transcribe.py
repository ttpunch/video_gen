import pytest

import transcribe


class _FakeWord:
    def __init__(self, word, start, end):
        self.word = word
        self.start = start
        self.end = end


class _FakeSegment:
    def __init__(self, words):
        self.words = words


class _FakeModel:
    """Stands in for faster_whisper.WhisperModel."""
    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio_path, word_timestamps=False):
        return iter(self._segments), {"language": "en"}


def test_extract_words_flattens_segments():
    segs = [
        _FakeSegment([_FakeWord(" Hello", 0.0, 0.4), _FakeWord(" world", 0.4, 0.8)]),
        _FakeSegment([_FakeWord(" again", 0.8, 1.1)]),
    ]
    words = transcribe._extract_words(segs)
    assert [w["word"] for w in words] == ["Hello", "world", "again"]
    assert words[0]["start"] == 0.0 and words[0]["end"] == 0.4


def test_extract_words_skips_blank_or_timeless():
    segs = [_FakeSegment([
        _FakeWord("  ", 0.0, 0.4),       # blank
        _FakeWord("ok", None, 0.8),      # missing start
        _FakeWord("good", 0.8, 1.0),
    ])]
    words = transcribe._extract_words(segs)
    assert [w["word"] for w in words] == ["good"]


def test_transcribe_words_uses_injected_model(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF....")  # contents irrelevant; the fake model ignores them
    model = _FakeModel([_FakeSegment([_FakeWord("hi", 0.0, 0.5)])])

    words = transcribe.transcribe_words(str(audio), _model=model)
    assert words == [{"word": "hi", "start": 0.0, "end": 0.5}]


def test_transcribe_words_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        transcribe.transcribe_words("/no/such/file.wav", _model=object())
