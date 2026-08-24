"""Procedural background music for shorts.

Deliberately simple and unobtrusive: a warm pad with a sparse pluck melody. The
job is to fill silence under narration without drawing attention, so "boring but
consonant" beats "interesting but clashing" every time.

Three musical bugs made the earlier version sound awkward, all fixed here:

  * **The melody ignored the chord.** Notes were drawn at random from the whole
    scale while a chord sustained underneath, so roughly half of them landed a
    second or a tritone away from a chord tone. Melody notes are now chosen from
    the tones of whichever chord is currently sounding.
  * **Phrygian was in the random mode pool.** Its flattened second is the
    interval that makes music sound unsettled -- fine for horror, wrong for a
    facts video, and worse for being random between renders.
  * **The pad was low-passed at 300 Hz** while its roots sat at 73-110 Hz, so
    nothing survived but rumble. The filter now leaves the harmonics that make
    a pad read as warm rather than muddy.
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

#: Root notes (Hz). Low enough to sit under speech without masking it.
ROOTS = (73.42, 82.41, 87.31, 98.0, 110.0)   # D2, E2, F2, G2, A2

#: Only modes that read as calm//neutral. Phrygian is excluded on purpose --
#: its b2 sounds unsettled, and picking it at random made some videos feel wrong
#: for no reason the user could point at.
SCALES = {
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
}

#: Chord progression as scale degrees (0-indexed): i - VII - III - iv.
#: A restful minor loop that resolves back to the root.
#:
#: Degrees 1 and 5 are deliberately absent: each builds a DIMINISHED triad in
#: one of the two modes above (ii in natural minor, vi in dorian). A diminished
#: chord contains a tritone, which is the single most unsettling interval to
#: leave droning under a voiceover -- and because the mode is picked at random
#: per render, including them made only *some* videos sound wrong.
PROGRESSION = (0, 6, 2, 3)


def butter_lowpass(cutoff, fs, order=3):
    nyq = 0.5 * fs
    return butter(order, cutoff / nyq, btype="low", analog=False)


def lowpass_filter(data, cutoff, fs, order=3):
    b, a = butter_lowpass(cutoff, fs, order=order)
    return lfilter(b, a, data)


def _scale_freq(root, intervals, degree):
    """Frequency of a scale degree, wrapping into higher octaves as needed."""
    octave, index = divmod(degree, len(intervals))
    return root * (2 ** ((intervals[index] + 12 * octave) / 12.0))


def _triad(root, intervals, degree):
    """A chord built by stacking thirds -- degrees d, d+2, d+4, plus the octave.

    Stacking scale degrees two apart is what makes a triad; the earlier code
    stacked arbitrary indices, which produced clusters containing tritones.
    """
    return [_scale_freq(root, intervals, degree + step) for step in (0, 2, 4, 7)]


def generate_procedural_music(duration_sec, fs=24000, seed=None):
    """Return a mono float array of ambient backing music."""
    rng = np.random.default_rng(seed)
    root = float(rng.choice(ROOTS))
    intervals = SCALES[str(rng.choice(list(SCALES)))]

    total = int(fs * duration_sec)
    if total <= 0:
        return np.zeros(0, dtype=np.float32)

    chords = [_triad(root, intervals, d) for d in PROGRESSION]
    # Aim for ~6s per chord so a short cycles the progression once or twice,
    # rather than the whole loop being squeezed into one pass.
    chord_len = max(int(fs * 3.0), total // max(1, round(duration_sec / 6.0)))

    pad = np.zeros(total)
    melody = np.zeros(total)
    fade = int(fs * 1.2)

    chord_index = 0
    pos = 0
    while pos < total:
        seg = min(chord_len, total - pos)
        if seg <= 0:
            break
        chord = chords[chord_index % len(chords)]
        t = np.arange(seg) / fs

        # --- pad -------------------------------------------------------
        wave = np.zeros(seg)
        for freq in chord:
            wave += np.sin(2 * np.pi * freq * t)
            wave += 0.25 * np.sin(2 * np.pi * freq * 2 * t)
            wave += 0.08 * np.sin(2 * np.pi * freq * 3 * t)

        env = np.ones(seg)
        f = min(fade, seg // 2)
        if f > 0:
            env[:f] = np.linspace(0, 1, f)
            env[-f:] = np.linspace(1, 0, f)
        pad[pos:pos + seg] += wave * env

        # --- melody, locked to the chord that is actually sounding ------
        # Two octaves up so the plucks sit above the narration's fundamental
        # range instead of fighting it.
        options = [f * 4 for f in chord]
        beat = int(fs * 60.0 / 76.0)          # steady 76 BPM
        note_pos = int(fs * 0.5)
        while note_pos < seg - beat:
            freq = float(rng.choice(options))
            length = min(int(fs * 1.4), seg - note_pos)
            nt = np.arange(length) / fs
            pluck = np.sin(2 * np.pi * freq * nt) * np.exp(-nt * 5.0)
            # Simple feedback delay for space.
            d = int(fs * 0.3)
            if length > d:
                pluck[d:] += pluck[:-d] * 0.4
            melody[pos + note_pos:pos + note_pos + length] += pluck
            # Sparse but regular: every 2 or 4 beats, never syncopated randomly.
            note_pos += int(rng.choice([2, 4])) * beat

        pos += seg
        chord_index += 1

    # 800 Hz keeps the pad warm while still letting its harmonics through; the
    # old 300 Hz cut everything above the fundamentals and left only rumble.
    pad = lowpass_filter(pad, 800.0, fs, order=3)
    melody = lowpass_filter(melody, 2500.0, fs, order=2)

    mix = pad * 0.30 + melody * 0.10
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0:
        # Quiet by design. The render also sidechain-ducks this under speech.
        mix = mix / peak * 0.18
    return mix.astype(np.float32)


def write_procedural_music(duration_sec, output_path, fs=24000, seed=None):
    """Generate music and write it to ``output_path`` as a WAV."""
    data = generate_procedural_music(duration_sec, fs, seed=seed)
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    sf.write(output_path, data, fs)
    return output_path
