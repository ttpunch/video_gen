import os
import sys
import numpy as np
import soundfile as sf
from dotenv import load_dotenv

sys.path.append("/Volumes/MACEXSTORAGE/video_gen")
load_dotenv("/Volumes/MACEXSTORAGE/video_gen/.env")

from long_video_pipeline import run_long_video_pipeline

def test_pipeline_audio():
    pexels_key = os.getenv("PEXELS_API_KEY")
    
    # Construct a 2-scene storyboard
    storyboard = [
        {
            "scene": 1,
            "speaker": "Sarah",
            "narration": "Deep in the ocean, sunlight fails completely, leaving a realm of eternal darkness and crushing pressure.",
            "visual_prompt": "underwater dark ocean"
        },
        {
            "scene": 2,
            "speaker": "Sarah",
            "narration": "Here, strange and beautiful creatures glowing with bioluminescence navigate the silent abyss.",
            "visual_prompt": "bioluminescent jellyfish glowing"
        }
    ]
    
    print("Running pipeline...")
    final_output, updated_storyboard = run_long_video_pipeline(
        generation_id="audio_test",
        storyboard=storyboard,
        pexels_api_key=pexels_key,
        music_style="Cinematic",
        enable_captions=False
    )
    
    print(f"\nFinal output saved to: {final_output}")
    
    # The working dir was temp/long_audio_test
    working_dir = os.path.abspath("temp/long_audio_test")
    print(f"Working directory: {working_dir}")
    
    # List files in working directory
    files = os.listdir(working_dir)
    print("\nFiles in temp/long_audio_test:")
    for f in files:
        print(f" - {f}")
        
    def check_audio_rms(path, label):
        if os.path.exists(path):
            data, samplerate = sf.read(path)
            rms = np.sqrt(np.mean(data ** 2))
            db = 20 * np.log10(rms + 1e-9)
            print(f"🔊 {label} ({os.path.basename(path)}): RMS = {rms:.5f} ({db:.1f} dB), sample rate = {samplerate}")
        else:
            print(f"❌ {label} ({path}) does not exist.")
            
    # Find generated WAV files in working_dir
    scene_audios = sorted([os.path.join(working_dir, f) for f in files if f.startswith("scene_audio_")])
    for idx, sa in enumerate(scene_audios):
        check_audio_rms(sa, f"Scene {idx+1} Raw Audio")
        
    merged_audios = [os.path.join(working_dir, f) for f in files if f.startswith("merged_audio_")]
    for ma in merged_audios:
        check_audio_rms(ma, "Merged Audio")
        
    audio_mixeds = [os.path.join(working_dir, f) for f in files if f.startswith("audio_mixed_")]
    for am in audio_mixeds:
        check_audio_rms(am, "Audio Mixed with Music")
        
    audio_final_mixeds = [os.path.join(working_dir, f) for f in files if f.startswith("audio_final_mixed_")]
    for afm in audio_final_mixeds:
        check_audio_rms(afm, "Final Mixed Audio (with SFX)")

if __name__ == "__main__":
    test_pipeline_audio()
