import os
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

def butter_bandpass(lowcut, highcut, fs, order=3):
    nyq = 0.5 * fs
    # Ensure frequencies are within Nyquist limits
    lowcut = max(20.0, min(lowcut, nyq - 50.0))
    highcut = max(lowcut + 20.0, min(highcut, nyq - 20.0))
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def generate_whoosh_sfx(fs=24000):
    """Generate a clean wind-like whoosh sound using bandpass swept white noise."""
    duration = 0.8  # seconds
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    
    # 1. Generate white noise
    noise = np.random.normal(0, 0.2, len(t))
    
    # 2. Filter the noise with a time-varying bandpass center frequency
    # We slice the noise into small chunks and filter each chunk with a sweeping bandpass filter
    chunk_size = int(fs * 0.01)  # 10ms chunks
    num_chunks = len(noise) // chunk_size
    filtered_chunks = []
    
    for i in range(num_chunks):
        chunk_start = i * chunk_size
        chunk_end = chunk_start + chunk_size
        chunk = noise[chunk_start:chunk_end]
        
        # Center frequency sweeps from 250Hz up to 2000Hz (first half), then down to 250Hz (second half)
        progress = i / num_chunks
        if progress < 0.5:
            # Sweep up
            center_freq = 250 + (1750 * (progress * 2))
        else:
            # Sweep down
            center_freq = 2000 - (1750 * ((progress - 0.5) * 2))
            
        bandwidth = 300
        lowcut = center_freq - bandwidth/2
        highcut = center_freq + bandwidth/2
        
        try:
            b, a = butter_bandpass(lowcut, highcut, fs, order=2)
            filtered_chunk = lfilter(b, a, chunk)
        except Exception:
            filtered_chunk = chunk * 0.1  # fallback
            
        filtered_chunks.append(filtered_chunk)
        
    # Reassemble and pad if necessary
    filtered_noise = np.concatenate(filtered_chunks)
    if len(filtered_noise) < len(noise):
        filtered_noise = np.pad(filtered_noise, (0, len(noise) - len(filtered_noise)), 'constant')
        
    # 3. Apply volume envelope (Hanning-like rise and fall)
    envelope = np.sin(np.pi * (t / duration)) ** 2
    whoosh = filtered_noise * envelope
    
    # Normalize
    max_val = np.max(np.abs(whoosh))
    if max_val > 0:
        whoosh = whoosh / max_val * 0.8
        
    return whoosh

def generate_pop_sfx(fs=24000):
    """Generate a quick 'pop' or 'ding' sound using a decaying sine wave."""
    duration = 0.15  # seconds
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    
    # 1. Generate sine wave at 980Hz
    freq = 980.0
    sine = np.sin(2 * np.pi * freq * t)
    
    # 2. Apply exponential decay envelope
    envelope = np.exp(-t * 22)
    pop = sine * envelope
    
    # Normalize
    max_val = np.max(np.abs(pop))
    if max_val > 0:
        pop = pop / max_val * 0.5
        
    return pop

def build_sfx_assets():
    """Synthesize and write WAV files to assets/sfx/ directory."""
    sfx_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "sfx"))
    os.makedirs(sfx_dir, exist_ok=True)
    
    fs = 24000
    
    whoosh_path = os.path.join(sfx_dir, "whoosh.wav")
    whoosh_data = generate_whoosh_sfx(fs)
    sf.write(whoosh_path, whoosh_data, fs)
    print(f"Generated whoosh transition SFX: {whoosh_path}")
    
    pop_path = os.path.join(sfx_dir, "pop.wav")
    pop_data = generate_pop_sfx(fs)
    sf.write(pop_path, pop_data, fs)
    print(f"Generated active pop highlight SFX: {pop_path}")

if __name__ == "__main__":
    build_sfx_assets()
