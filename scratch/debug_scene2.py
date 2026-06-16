import os
import sys
import subprocess
from dotenv import load_dotenv

sys.path.append("/Volumes/MACEXSTORAGE/video_gen")
load_dotenv("/Volumes/MACEXSTORAGE/video_gen/.env")

from long_video_pipeline import search_pexels_video, download_video_file

def debug():
    pexels_key = os.getenv("PEXELS_API_KEY")
    query = "calm ocean surface sunlight reflection water ripples"
    os.makedirs("temp_test", exist_ok=True)
    raw_video_path = "temp_test/raw_scene2.mp4"
    
    url = search_pexels_video(query, pexels_key, orientation="landscape")
    print(f"URL: {url}")
    download_video_file(url, raw_video_path)
    
    # Let's see the duration of the downloaded raw video
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", raw_video_path
    ]
    duration = subprocess.check_output(cmd).decode().strip()
    print(f"Raw Video Duration: {duration}s")
    
    # Dummy audio of 14.25 seconds
    sc_audio_path = "temp_test/dummy_scene2.wav"
    # Generate 14.25s silence
    cmd_audio = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", "14.25", sc_audio_path
    ]
    subprocess.run(cmd_audio, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Run the FFmpeg command exactly as in the pipeline, but don't redirect stderr
    scene_segment_path = "temp_test/segment_scene2.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-an", "-i", raw_video_path,
        "-i", sc_audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", "14.25",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        scene_segment_path
    ]
    print("Running FFmpeg:")
    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    print("STDOUT:")
    print(res.stdout)
    print("STDERR:")
    print(res.stderr)

if __name__ == "__main__":
    debug()
