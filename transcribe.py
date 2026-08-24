"""Word-level speech transcription for audio-aligned captions.

Uses faster-whisper (CTranslate2) when available. The model is loaded lazily and
cached, so importing this module is cheap and the dependency is optional: if it
isn't installed the caller falls back to estimated caption timing.

Configuration:
    WHISPER_MODEL    Model size: tiny | base | small | medium (default 'base').
    WHISPER_DEVICE   'cpu' (default) or 'cuda'.
"""
import os

_MODEL_CACHE = {}


class TranscriptionUnavailable(Exception):
    """Raised when no transcription backend is installed/usable."""


def _extract_words(segments):
    """Flatten faster-whisper segments into ``[{word, start, end}]``.

    Pure and backend-agnostic: ``segments`` is any iterable of objects exposing a
    ``.words`` iterable of objects with ``.word`` / ``.start`` / ``.end``.
    """
    words = []
    for seg in segments:
        for w in (getattr(seg, "words", None) or []):
            token = (getattr(w, "word", "") or "").strip()
            start = getattr(w, "start", None)
            end = getattr(w, "end", None)
            if not token or start is None or end is None:
                continue
            words.append({"word": token, "start": float(start), "end": float(end)})
    return words


def _get_model(model_size, device, compute_type):
    key = (model_size, device, compute_type)
    if key not in _MODEL_CACHE:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise TranscriptionUnavailable(
                "faster-whisper is not installed (pip install faster-whisper)"
            ) from e
        _MODEL_CACHE[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _MODEL_CACHE[key]


def transcribe_words(audio_path, model_size=None, device=None, _model=None):
    """Return word-level timestamps for ``audio_path`` as ``[{word, start, end}]``.

    ``_model`` is an injection point for tests; production resolves the cached
    faster-whisper model. Raises TranscriptionUnavailable if no backend exists.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model_size = model_size or os.getenv("WHISPER_MODEL", "base")
    device = device or os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = "int8" if device == "cpu" else "float16"

    model = _model or _get_model(model_size, device, compute_type)
    segments, _info = model.transcribe(audio_path, word_timestamps=True)
    return _extract_words(segments)
