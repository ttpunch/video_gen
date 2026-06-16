import subprocess
import os
import soundfile as sf
import numpy as np

def analyze():
    video = "outputs/long_reel_1781409247.mp4"
    audio_wav = "temp_test_audio.wav"
    if os.path.exists(audio_wav):
        os.remove(audio_wav)
        
    # Extract audio to WAV
    cmd = ["ffmpeg", "-y", "-i", video, "-c:a", "pcm_s16le", audio_wav]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not os.path.exists(audio_wav):
        print("❌ Failed to extract audio.")
        return
        
    data, samplerate = sf.read(audio_wav)
    print(f"Sample Rate: {samplerate} Hz")
    print(f"Data shape: {data.shape}")
    print(f"Total duration: {len(data)/samplerate:.2f} seconds")
    
    # Calculate energy in 5-second chunks
    chunk_size = samplerate * 5
    num_chunks = len(data) // chunk_size
    print("\nEnergy level of audio in 5-second chunks:")
    for i in range(num_chunks):
        start = i * chunk_size
        end = start + chunk_size
        chunk_data = data[start:end]
        rms = np.sqrt(np.mean(chunk_data ** 2))
        db = 20 * np.log10(rms + 1e-9)
        print(f"Chunk {i+1} ({i*5}s to {(i+1)*5}s): RMS = {rms:.5f} ({db:.1f} dB)")
        
    os.remove(audio_wav)

if __name__ == "__main__":
    analyze()
