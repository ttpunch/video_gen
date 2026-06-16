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
        return hashlib.md5(data).hexdigest()
    return None

def test_loop_exact():
    video = "temp_test/output_fallback_looped.mp4"
    h_1 = get_image_hash("1.0", video)
    h_9_9 = get_image_hash("9.9", video)
    h_8_9 = get_image_hash("8.9", video)
    h_17_8 = get_image_hash("17.8", video)
    h_20_0 = get_image_hash("20.0", video)
    h_25_0 = get_image_hash("25.0", video)
    
    print(f"Hash 1.0s:  {h_1}")
    print(f"Hash 9.9s:  {h_9_9}")
    print(f"Hash 8.9s:  {h_8_9}")
    print(f"Hash 17.8s: {h_17_8}")
    print(f"Hash 20.0s: {h_20_0}")
    print(f"Hash 25.0s: {h_25_0}")
    
    if h_1 == h_9_9:
        print("✅ Loop test passed: 1.0s and 9.9s are identical!")
    else:
        print("❌ Loop test failed: 1.0s and 9.9s are different.")
        
    if h_8_9 == h_17_8:
        print("✅ Loop test passed: 8.9s and 17.8s are identical!")
    else:
        print("❌ Loop test failed: 8.9s and 17.8s are different.")
        
    if h_8_9 == h_20_0:
        print("⚠️ 8.9s and 20.0s are identical (frozen!).")
    if h_8_9 == h_25_0:
        print("⚠️ 8.9s and 25.0s are identical (frozen!).")

if __name__ == "__main__":
    test_loop_exact()
