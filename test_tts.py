import os
import requests
from tqdm import tqdm

def download_file(url, dest_path):
    print(f"Downloading {os.path.basename(dest_path)} from {url}...")
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024 * 1024 # 1MB
    
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    with open(dest_path, 'wb') as f, tqdm(
        total=total_size, unit='iB', unit_scale=True, desc=os.path.basename(dest_path)
    ) as progress_bar:
        for data in response.iter_content(block_size):
            progress_bar.update(len(data))
            f.write(data)
    print("Download complete.")

def main():
    # Setup paths
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    
    onnx_path = os.path.join(models_dir, "kokoro-v1.0.onnx")
    voices_path = os.path.join(models_dir, "voices-v1.0.bin")
    
    # Download URLs
    onnx_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
    
    # Check and download
    if not os.path.exists(onnx_path):
        download_file(onnx_url, onnx_path)
    else:
        print("✅ Kokoro ONNX model already exists.")
        
    if not os.path.exists(voices_path):
        download_file(voices_url, voices_path)
    else:
        print("✅ Voices binary file already exists.")
        
    # Test TTS generation
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf
        
        print("\nInitializing Kokoro model...")
        kokoro = Kokoro(onnx_path, voices_path)
        
        text = "Hello! This is a test of the local Kokoro TTS model running on your M4 Mac Mini. It works perfectly!"
        voice = "af_sarah" # Female American voice
        
        print(f"Synthesizing audio using voice '{voice}'...")
        samples, sample_rate = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
        
        output_path = os.path.join(os.path.dirname(__file__), "test_tts_output.wav")
        sf.write(output_path, samples, sample_rate)
        print(f"✅ Audio generated successfully! Saved to: {output_path}")
        
    except ImportError as e:
        print(f"❌ Could not import required packages: {e}")
        print("Ensure you have run pip install -r requirements.txt first.")
    except Exception as e:
        print(f"❌ Error during synthesis: {e}")

if __name__ == "__main__":
    main()
