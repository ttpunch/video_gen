import os
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

def butter_lowpass(cutoff, fs, order=3):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a

def lowpass_filter(data, cutoff, fs, order=3):
    b, a = butter_lowpass(cutoff, fs, order=order)
    return lfilter(b, a, data)

def generate_procedural_music(duration_sec, fs=24000):
    """Generates a warm, ambient, unique background music track procedurally."""
    # 1. Define scales and keys (Minor, Major, Dorian, Phrygian modes)
    # We choose a root note frequency and generate a scale dynamically.
    # Standard roots (Hz): D2=73.42, E2=82.41, F2=87.31, G2=98.0, A2=110.0
    roots = [73.42, 82.41, 87.31, 98.0, 110.0]
    root_freq = np.random.choice(roots)
    
    # Scale intervals in semitones (0 is root)
    scale_types = {
        "Natural_Minor": [0, 2, 3, 5, 7, 8, 10, 12, 14, 15, 17, 19, 20, 22, 24],
        "Dorian": [0, 2, 3, 5, 7, 9, 10, 12, 14, 15, 17, 19, 21, 22, 24],
        "Phrygian": [0, 1, 3, 5, 7, 8, 10, 12, 13, 15, 17, 19, 20, 22, 24],
        "Major_Pentatonic": [0, 2, 4, 7, 9, 12, 14, 16, 19, 21, 24, 26, 28, 31, 33]
    }
    
    scale_name = np.random.choice(list(scale_types.keys()))
    intervals = scale_types[scale_name]
    
    # Compute the actual frequencies for the chosen scale
    # f = f0 * 2^(n/12)
    scale_notes = [root_freq * (2 ** (n / 12.0)) for n in intervals]
    
    total_samples = int(fs * duration_sec)
    mix = np.zeros(total_samples)
    
    # 2. Generate Ambient Pad Chords (Warm pad progression)
    # We choose 4 chords based on scale indices
    # Progression: i - IV - v - VI (or standard variants depending on scale)
    chord_duration = duration_sec / 4.0
    chord_samples = int(fs * chord_duration)
    
    # Generate 4 distinct chord frequency sets based on the scale
    progressions = []
    # Root chord (1, 3, 5, 8)
    progressions.append([scale_notes[0], scale_notes[2], scale_notes[4], scale_notes[7]])
    # 4th chord (3, 5, 7, 10)
    progressions.append([scale_notes[3], scale_notes[5], scale_notes[7], scale_notes[10]])
    # 5th chord or 6th chord (5, 7, 9, 12)
    progressions.append([scale_notes[4], scale_notes[6], scale_notes[8], scale_notes[11]])
    # Subdominant / Relative chord (6, 8, 10, 13)
    progressions.append([scale_notes[5], scale_notes[7], scale_notes[9], scale_notes[12]])
    
    pad_signal = np.zeros(total_samples)
    for i in range(4):
        start_sample = i * chord_samples
        end_sample = min(start_sample + chord_samples, total_samples)
        seg_len = end_sample - start_sample
        if seg_len <= 0:
            break
            
        t = np.linspace(0, seg_len / fs, seg_len, endpoint=False)
        chord_wave = np.zeros(seg_len)
        chord_freqs = progressions[i % len(progressions)]
        
        # Add fundamental + octave + soft harmonics
        for freq in chord_freqs:
            chord_wave += np.sin(2 * np.pi * freq * t)
            chord_wave += 0.25 * np.sin(2 * np.pi * (freq * 2) * t)
            chord_wave += 0.1 * np.sin(2 * np.pi * (freq * 3) * t)
            
        # Apply slow attack/release envelope
        envelope = np.ones(seg_len)
        fade_samples = int(fs * 1.5)  # 1.5s crossfade
        if fade_samples > seg_len // 2:
            fade_samples = seg_len // 2
            
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        
        pad_signal[start_sample:end_sample] += chord_wave * envelope
        
    # Low-pass filter the pad to make it extremely warm and soft
    pad_signal = lowpass_filter(pad_signal, 300.0, fs, order=3)
    mix += pad_signal * 0.12  # Soft pad volume
    
    # 3. Generate a Soft Pluck Melody
    melody_signal = np.zeros(total_samples)
    
    # Random tempo (BPM)
    tempo_bpm = np.random.randint(70, 90)
    beat_dur = 60.0 / tempo_bpm
    beat_samples = int(fs * beat_dur)
    
    # Generate plucks on random beats
    current_sample = int(fs * 1.5)  # Let pad fade in first
    melody_notes = [n for n in scale_notes if n >= 220.0]  # Higher register notes only
    
    while current_sample < total_samples - int(fs * 2.0):
        # Choose a random note
        note_freq = np.random.choice(melody_notes)
        
        pluck_len = int(fs * 1.0)
        if current_sample + pluck_len > total_samples:
            pluck_len = total_samples - current_sample
            
        t = np.linspace(0, pluck_len / fs, pluck_len, endpoint=False)
        # Exponential decay envelope
        decay = np.exp(-t * 8.0)
        pluck_wave = np.sin(2 * np.pi * note_freq * t) * decay
        
        # Delay effect (plucks feed into a simple delay loop)
        delay_samples = int(fs * 0.3)
        if pluck_len > delay_samples:
            pluck_wave[delay_samples:] += pluck_wave[:-delay_samples] * 0.45
            
        melody_signal[current_sample:current_sample+pluck_len] += pluck_wave
        
        # Step forward by 1, 2, or 4 beats
        step = np.random.choice([1, 2, 4])
        current_sample += step * beat_samples
        
    # Low-pass filter the melody so it sounds like warm rhodes/bells
    melody_signal = lowpass_filter(melody_signal, 1000.0, fs, order=2)
    mix += melody_signal * 0.055  # Pluck volume
    
    # 4. Final normalization to optimal background level
    max_val = np.max(np.abs(mix))
    if max_val > 0:
        # Normalize to target background level (avoid clipping narration)
        mix = mix / max_val * 0.14
        
    return mix

def write_procedural_music(duration_sec, output_path, fs=24000):
    """Generates procedural music and writes it directly to disk as a WAV file."""
    music_data = generate_procedural_music(duration_sec, fs)
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sf.write(output_path, music_data, fs)
    return output_path
