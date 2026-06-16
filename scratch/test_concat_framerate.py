import os
import sys
import subprocess
import hashlib
from dotenv import load_dotenv

sys.path.append("/Volumes/MACEXSTORAGE/video_gen")
load_dotenv("/Volumes/MACEXSTORAGE/video_gen/.env")

from long_video_pipeline import search_pexels_video, download_video_file

def test_framerate():
    pexels_key = os.getenv("PEXELS_API_KEY")
    os.makedirs("temp_test", exist_ok=True)
    
    # Let's search for two different queries to get two different videos (which likely have different framerates)
    video1_raw = "temp_test/raw_v1.mp4"
    video2_raw = "temp_test/raw_v2.mp4"
    
    url1 = search_pexels_video("aerial ocean blue water", pexels_key, orientation="landscape")
    url2 = search_pexels_video("underwater sun rays", pexels_key, orientation="landscape")
    
    download_video_file(url1, video1_raw)
    download_video_file(url2, video2_raw)
    
    # Check framerates of raw videos
    def get_fps(path):
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ]
        return subprocess.check_output(cmd).decode().strip()
        
    print(f"Video 1 raw FPS: {get_fps(video1_raw)}")
    print(f"Video 2 raw FPS: {get_fps(video2_raw)}")
    
    # Synthesize dummy audio for both
    audio1 = "temp_test/audio_v1.wav"
    audio2 = "temp_test/audio_v2.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "5", audio1], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "5", audio2], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Method A: Without standardizing frame rate
    seg1_a = "temp_test/seg1_a.mp4"
    seg2_a = "temp_test/seg2_a.mp4"
    
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-an", "-i", video1_raw, "-i", audio1,
        "-map", "0:v:0", "-map", "1:a:0", "-t", "5",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", seg1_a
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-an", "-i", video2_raw, "-i", audio2,
        "-map", "0:v:0", "-map", "1:a:0", "-t", "5",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", seg2_a
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Method B: With standardizing frame rate to 30 fps
    seg1_b = "temp_test/seg1_b.mp4"
    seg2_b = "temp_test/seg2_b.mp4"
    
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-an", "-i", video1_raw, "-i", audio1,
        "-map", "0:v:0", "-map", "1:a:0", "-t", "5",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", seg1_b
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-an", "-i", video2_raw, "-i", audio2,
        "-map", "0:v:0", "-map", "1:a:0", "-t", "5",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", seg2_b
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Concat Method A
    list_a = "temp_test/list_a.txt"
    with open(list_a, "w") as f:
        f.write(f"file '{os.path.abspath(seg1_a)}'\n")
        f.write(f"file '{os.path.abspath(seg2_a)}'\n")
    concat_a = "temp_test/concat_a.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_a, "-c", "copy", concat_a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Concat Method B
    list_b = "temp_test/list_b.txt"
    with open(list_b, "w") as f:
        f.write(f"file '{os.path.abspath(seg1_b)}'\n")
        f.write(f"file '{os.path.abspath(seg2_b)}'\n")
    concat_b = "temp_test/concat_b.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_b, "-c", "copy", concat_b], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Now check if the frames in second clip of concat_a and concat_b are frozen!
    # Clip 1 is 0-5s, Clip 2 is 5-10s. Let's check frames at 6s, 7s, 8s, 9s.
    def check_frozen(path):
        hashes = []
        for sec in [6, 7, 8, 9]:
            out_img = f"temp_test/frame_check_{sec}.png"
            if os.path.exists(out_img):
                os.remove(out_img)
            subprocess.run(["ffmpeg", "-y", "-ss", str(sec), "-i", path, "-vframes", "1", out_img], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(out_img):
                with open(out_img, "rb") as f:
                    hashes.append(hashlib.md5(f.read()).hexdigest())
        return hashes
        
    hashes_a = check_frozen(concat_a)
    hashes_b = check_frozen(concat_b)
    
    print("\nMethod A (No standardised FPS) hashes (6s, 7s, 8s, 9s):", hashes_a)
    print("Method A frozen?", len(set(hashes_a)) == 1)
    
    print("\nMethod B (30 FPS standardized) hashes (6s, 7s, 8s, 9s):", hashes_b)
    print("Method B frozen?", len(set(hashes_b)) == 1)

if __name__ == "__main__":
    test_framerate()
