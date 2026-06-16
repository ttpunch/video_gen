import subprocess
import os

def check():
    video = "outputs/long_reel_1781409833.mp4"
    if not os.path.exists(video):
        print("❌ Video does not exist.")
        return
        
    cmd = ["ffmpeg", "-i", video, "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("Volume detection of final output:")
    for line in res.stderr.split("\n"):
        if "volume" in line.lower():
            print(line)

if __name__ == "__main__":
    check()
