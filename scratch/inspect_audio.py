import subprocess
import os

def inspect():
    video = "outputs/long_reel_1781409247.mp4"
    if not os.path.exists(video):
        print(f"❌ Video {video} does not exist.")
        return
        
    # Check stream information
    cmd = [
        "ffprobe", "-v", "error", "-show_streams", "-select_streams", "a",
        "-of", "json", video
    ]
    info = subprocess.check_output(cmd).decode()
    print("Audio stream info:")
    print(info)
    
    # Let's run volumedetect filter on the audio
    cmd_vol = [
        "ffmpeg", "-i", video, "-af", "volumedetect", "-f", "null", "-"
    ]
    res = subprocess.run(cmd_vol, capture_output=True, text=True)
    print("\nVolume detection output:")
    # Print lines containing max_volume, mean_volume
    for line in res.stderr.split("\n"):
        if "volume" in line.lower():
            print(line)

if __name__ == "__main__":
    inspect()
