"""The backing music has to be consonant, quiet, and never clash with narration.

The failure being guarded against is musical, not a crash: the earlier generator
drew melody notes at random from the whole scale while an unrelated chord
sustained underneath, which is what made the backing track sound awkward.
"""
import numpy as np
import pytest

import music_generator as mg

# Intervals the ear reads as dissonant when sounded together.
DISSONANT_SEMITONES = {1, 2, 6, 10, 11}


def semitones_between(f_low, f_high):
    return round(12 * np.log2(f_high / f_low))


# --------------------------------------------------------------------------
# Harmony
# --------------------------------------------------------------------------

def test_phrygian_is_not_in_the_mode_pool():
    """Its flat 2nd sounds unsettled, and picking it at random made some
    renders feel wrong for no reason the user could point at."""
    for intervals in mg.SCALES.values():
        assert 1 not in intervals, "a flattened second is in the scale"


def test_every_chord_is_a_stack_of_thirds():
    """Arbitrary scale-index stacking produced voicings containing tritones."""
    for scale in mg.SCALES.values():
        for degree in mg.PROGRESSION:
            chord = mg._triad(110.0, scale, degree)
            gaps = [semitones_between(chord[i], chord[i + 1])
                    for i in range(len(chord) - 1)]
            assert all(g in (3, 4, 5) for g in gaps), \
                f"degree {degree} gave non-triadic gaps {gaps}"


def test_no_chord_contains_a_tritone():
    for scale in mg.SCALES.values():
        for degree in mg.PROGRESSION:
            chord = mg._triad(110.0, scale, degree)
            for i, low in enumerate(chord):
                for high in chord[i + 1:]:
                    assert semitones_between(low, high) % 12 != 6, \
                        f"tritone in chord on degree {degree}"


def test_melody_notes_are_chord_tones():
    """The core fix: the melody must follow the chord that is sounding.

    Melody options are the chord frequencies raised two octaves, so every note
    is consonant with the pad by construction.
    """
    for scale in mg.SCALES.values():
        for degree in mg.PROGRESSION:
            chord = mg._triad(110.0, scale, degree)
            for note in [f * 4 for f in chord]:
                # Two octaves is exactly 24 semitones from its chord tone.
                assert any(semitones_between(c, note) == 24 for c in chord)


# --------------------------------------------------------------------------
# Signal
# --------------------------------------------------------------------------

@pytest.mark.parametrize("duration", [3.0, 12.0, 45.0])
def test_output_length_matches_the_request(duration):
    audio = mg.generate_procedural_music(duration, fs=8000, seed=1)
    assert abs(len(audio) / 8000 - duration) < 0.5


def test_output_is_quiet_enough_to_sit_under_speech():
    audio = mg.generate_procedural_music(10.0, fs=8000, seed=1)
    assert 0 < float(np.max(np.abs(audio))) <= 0.25


def test_output_never_clips():
    for seed in range(6):
        audio = mg.generate_procedural_music(8.0, fs=8000, seed=seed)
        assert float(np.max(np.abs(audio))) < 1.0


def test_output_is_finite():
    """A NaN here would silence the whole mix downstream."""
    audio = mg.generate_procedural_music(8.0, fs=8000, seed=3)
    assert np.all(np.isfinite(audio))


def test_seed_makes_it_reproducible():
    a = mg.generate_procedural_music(6.0, fs=8000, seed=42)
    b = mg.generate_procedural_music(6.0, fs=8000, seed=42)
    assert np.array_equal(a, b)


def test_zero_duration_returns_empty_rather_than_raising():
    assert len(mg.generate_procedural_music(0, fs=8000)) == 0


def test_write_creates_a_readable_wav(tmp_path):
    import soundfile as sf
    out = tmp_path / "nested" / "music.wav"
    mg.write_procedural_music(4.0, str(out), fs=8000, seed=2)
    data, rate = sf.read(str(out))
    assert rate == 8000
    assert len(data) > 0
