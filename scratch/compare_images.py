from PIL import Image
import numpy as np

def compare():
    img1 = Image.open("temp_test/frame_20_0.png")
    img2 = Image.open("temp_test/frame_25_0.png")
    img3 = Image.open("temp_test/frame_8_0.png")
    
    arr1 = np.array(img1)
    arr2 = np.array(img2)
    arr3 = np.array(img3)
    
    diff_20_25 = np.sum(np.abs(arr1.astype(float) - arr2.astype(float)))
    diff_8_20 = np.sum(np.abs(arr3.astype(float) - arr1.astype(float)))
    
    print(f"Pixel difference between 20s and 25s: {diff_20_25}")
    print(f"Pixel difference between 8s and 20s: {diff_8_20}")

if __name__ == "__main__":
    compare()
