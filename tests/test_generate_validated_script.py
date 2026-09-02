"""generate_validated_script's retry loop: mechanical fixes avoid burning a
second LLM round trip, and an overall deadline returns the least-bad attempt
instead of leaving the caller waiting through a full final attempt for a
result that then still gets discarded.

Reproduced live: a 2026-08-31 failure_alerts.log entry shows "The $16 Million
Violin" topic dying after 3 full attempts on hook-length validation alone --
exactly the class of issue mechanically_fix_hard_issues now corrects in place.
"""
import time

import pytest

import backend


def _script(narration_lines, hook=None, subject_focus="vivid pink flamingos wading in a shallow lagoon"):
    narrs = list(narration_lines)
    if hook is not None:
        narrs[0] = hook
    return {
        "topic": "t",
        "global_visual_style": "photorealistic, natural lighting",
        # Named here (not just in the default hook line) so swapping the hook
        # in a test doesn't accidentally strip the only topic-word occurrence
        # and trip an unrelated off-topic failure.
        "global_subject_focus": subject_focus,
        "scenes": [
            {"speaker": "Sarah", "narration": n, "visual_prompt": f"a realistic scene of {n}"}
            for n in narrs
        ],
    }


GOOD_NARRATION = [
    "Flamingos aren't born pink at all.",
    "They actually hatch a dull gray color.",
    "The secret comes entirely from their diet.",
    "They eat brine shrimp packed with beta-carotene.",
    "Their liver breaks down that bright pigment.",
    "It slowly paints every single feather pink.",
    "Follow for more wild nature facts.",
]


def test_mechanical_fix_avoids_a_second_generation_call(monkeypatch):
    """An over-length hook must be fixed in place, not trigger a regeneration."""
    long_hook = (
        "So today I wanted to sit down and actually properly explain to you "
        "exactly why this topic works the way that it does."
    )
    calls = {"n": 0}

    def fake_generate(*a, **k):
        calls["n"] += 1
        return _script(GOOD_NARRATION, hook=long_hook)

    monkeypatch.setattr(backend, "generate_ollama_script", fake_generate)
    # GOOD_NARRATION totals well under "Standard"'s 110-145 word floor; widen
    # the range so this test isolates the hook-length issue instead of also
    # tripping "too short" (a separate, unfixable-without-the-LLM issue).
    monkeypatch.setitem(backend.DURATION_PRESETS, backend.DEFAULT_DURATION_PRESET, (10, 200, "test"))

    result = backend.generate_validated_script("flamingos", "m", attempts=3, log=lambda *_: None)

    assert calls["n"] == 1, "a mechanically-fixable issue must not cost a second generation call"
    assert len(result["scenes"][0]["narration"].split()) <= 14
    assert "_validation_warnings" not in result


def test_deadline_returns_best_attempt_instead_of_raising(monkeypatch):
    """An unfixable issue (off-topic) that persists past the time budget must
    return the least-bad attempt with warnings, not raise after a wasted
    final attempt."""
    off_topic = ["Deep space contains many mysterious objects today."] * 7

    def fake_generate(*a, **k):
        time.sleep(0.05)
        return _script(off_topic, subject_focus="a distant galaxy")

    monkeypatch.setattr(backend, "generate_ollama_script", fake_generate)

    result = backend.generate_validated_script(
        "flamingos", "m", attempts=5, log=lambda *_: None, max_seconds=0.03,
    )

    assert "_validation_warnings" in result
    assert any("off-topic" in w for w in result["_validation_warnings"])


def test_raises_when_no_attempt_ever_produces_a_script(monkeypatch):
    def fake_generate(*a, **k):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr(backend, "generate_ollama_script", fake_generate)

    with pytest.raises(RuntimeError, match="failed viral validation"):
        backend.generate_validated_script("flamingos", "m", attempts=2, log=lambda *_: None)


def test_success_on_a_later_attempt_returns_clean_without_warnings(monkeypatch):
    attempts_seen = []

    def fake_generate(*a, **k):
        attempts_seen.append(1)
        if len(attempts_seen) == 1:
            return _script(["Deep space contains many mysterious objects today."] * 7,
                           subject_focus="a distant galaxy")
        return _script(GOOD_NARRATION)

    monkeypatch.setattr(backend, "generate_ollama_script", fake_generate)
    monkeypatch.setitem(backend.DURATION_PRESETS, backend.DEFAULT_DURATION_PRESET, (10, 200, "test"))

    result = backend.generate_validated_script("flamingos", "m", attempts=3, log=lambda *_: None)

    assert len(attempts_seen) == 2
    assert "_validation_warnings" not in result
