import subprocess
import hashlib
import os

def extract_frame(sec, video_path):
    out_img = f"temp_test/final_frame_{sec}.png"
    if os.path.exists(out_img):
        os.remove(out_img)
    cmd = [
        "ffmpeg", "-y", "-ss", str(sec), "-i", video_path,
        "-vframes", "1", out_img
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(out_img):
        with open(out_img, "rb") as f:
            data = f.read()
        return hashlib.md5(data).hexdigest(), out_img
    return None, None

def check():
    video = "outputs/long_reel_1781407883.mp4"
    if not os.path.exists(video):
        print(f"❌ Video {video} does not exist.")
        return
        
    os.makedirs("temp_test", exist_ok=True)
    
    # Scene 1 is from 0 to 12.92s. Let's check frames at seconds 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12.
    print("Checking Scene 1 (0s to 12s):")
    hashes = {}
    for sec in range(1, 13):
        h, path = extract_frame(sec, video)
        hashes[sec] = h
        print(f"Second {sec}s: hash = {h}")
        
    print("\nComparing frames in Scene 1:")
    consecutive_matches = 0
    for sec in range(1, 12):
        if hashes[sec] == hashes[sec+1]:
            print(f"⚠️ Frame at {sec}s is IDENTICAL to frame at {sec+1}s (frozen!)")
            consecutive_matches += 1
        else:
            print(f"✅ Frame at {sec}s is DIFFERENT from frame at {sec+1}s")
            
    # Scene 2 is from 12.92s to 27.17s. Let's check frames at 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26
    print("\nChecking Scene 2 (14s to 26s):")
    hashes2 = {}
    for sec in range(14, 27):
        h, path = extract_frame(sec, video)
        hashes2[sec] = h
        print(f"Second {sec}s: hash = {h}")
        
    print("\nComparing frames in Scene 2:")
    for sec in range(14, 26):
        if hashes2[sec] == hashes2[sec+1]:
            print(f"⚠️ Frame at {sec}s is IDENTICAL to frame at {sec+1}s (frozen!)")
        else:
            print(f"✅ Frame at {sec}s is DIFFERENT from frame at {sec+1}s")

if __name__ == "__main__":
    check()
