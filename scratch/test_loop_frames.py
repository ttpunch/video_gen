import subprocess
import hashlib
import os

def get_image_hash(timestamp, video_path):
    out_img = f"temp_test/frame_{timestamp.replace('.', '_')}.png"
    if os.path.exists(out_img):
        os.remove(out_img)
        
    cmd = [
        "ffmpeg", "-y", "-ss", timestamp, "-i", video_path,
        "-vframes", "1", out_img
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(out_img):
        with open(out_img, "rb") as f:
            data = f.read()
        return hashlib.md5(data).hexdigest(), out_img
    return None, None

def test_looping():
    video = "temp_test/output_fallback_looped.mp4"
    print(f"Testing video: {video}")
    
    timestamps = ["5.0", "8.0", "10.0", "15.0", "20.0", "25.0"]
    hashes = {}
    for ts in timestamps:
        h, img_path = get_image_hash(ts, video)
        hashes[ts] = (h, img_path)
        print(f"Timestamp {ts}s: hash = {h}")
        
    # Check if hashes of timestamps after 8.9s are identical to the hash at 8.0s or are unique
    print("\nComparing hashes:")
    for ts1, (h1, _) in hashes.items():
        for ts2, (h2, _) in hashes.items():
            if ts1 < ts2:
                if h1 == h2:
                    print(f"⚠️ Frame at {ts1}s is IDENTICAL to frame at {ts2}s (frozen!)")
                else:
                    print(f"✅ Frame at {ts1}s is DIFFERENT from frame at {ts2}s")

if __name__ == "__main__":
    test_looping()
