import os
import sys
import time
import json
import requests
import configparser
import subprocess
import soundfile as sf
import shutil
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

app = FastAPI(title="AI Video Presenter Backend", version="1.0.0")

# Enable CORS for Next.js app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure temp and outputs directories exist
os.makedirs("temp", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
os.makedirs(os.path.join("assets", "music"), exist_ok=True)
os.makedirs(os.path.join("assets", "satisfying"), exist_ok=True)

# Mount static files
app.mount("/temp", StaticFiles(directory="temp"), name="temp")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

KOKORO_VOICES = {
    "Sarah (Female - US - Soft)": "af_sarah",
    "Bella (Female - US - Warm)": "af_bella",
    "Nicole (Female - US - Energetic)": "af_nicole",
    "Sky (Female - US - Clear)": "af_sky",
    "Alloy (Female - US - Balanced)": "af_alloy",
    "Kore (Female - US - Playful)": "af_kore",
    "River (Female - US - Calm)": "af_river",
    "Adam (Male - US - Professional)": "am_adam",
    "Michael (Male - US - Corporate)": "am_michael",
    "Fenrir (Male - US - Deep)": "am_fenrir",
    "Puck (Male - US - Playful)": "am_puck",
    "Echo (Male - US - Clear)": "am_echo",
    "Liam (Male - US - Soft)": "am_liam",
    "Onyx (Male - US - Rich/Deep)": "am_onyx",
    "Emma (Female - UK - Elegant)": "bf_emma",
    "Isabella (Female - UK - Warm)": "bf_isabella",
    "George (Male - UK - Professional)": "bm_george",
    "Lewis (Male - UK - Soft)": "bm_lewis"
}

LEONARDO_MODELS = {
    "Leonardo Phoenix 1.0 (General/Realistic)": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",
    "Lucid Origin (Realistic Portrait)": "7b592283-e8a7-4c5a-9ba6-d18c31f258b9",
    "Lucid Realism (High Quality Face)": "05ce0082-2d80-4a2d-8653-4d1c85e2418e",
    "Flux Dev (SOTA Quality)": "b2614463-296c-462a-9586-aafdb8f00e36",
    "Leonardo Kino XL (Cinematic)": "aa77f04e-3eec-4034-9c07-d0f619684628",
    "Leonardo Vision XL (Artistic XL)": "5c232a9e-9061-4777-980a-ddc8e65647c6"
}

ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "16:9": (1024, 576),
    "9:16": (576, 1024),
    "4:3": (1024, 768),
    "3:2": (1024, 680)
}

MUSIC_PRESETS = {
    "Cinematic": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "Upbeat": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "Mysterious": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "Ambient": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3"
}

SATISFYING_PRESETS = {
    "Slime ASMR": "https://images.pexels.com/video-files/3129845/3129845-sd_540_960_25fps.mp4",
    "Kinetic Sand": "https://images.pexels.com/video-files/8566440/8566440-sd_540_960_30fps.mp4",
    "Satisfying Liquid": "https://images.pexels.com/video-files/8564860/8564860-sd_540_960_30fps.mp4"
}

VIRAL_HOOKS = {
    "None (Direct Prompt)": "",
    "Did You Know? (Fact Hook)": "Start the script with a mind-blowing 'Did you know...' hook in Scene 1 to grab immediate attention.",
    "3 Shocking Secrets": "Frame the script around '3 shocking secrets they don't want you to know', starting with a high-intensity hook in Scene 1.",
    "I Was Today Years Old": "Start the script with 'I was today years old when I found out this mind-blowing truth...' in Scene 1.",
    "This Changes Everything": "Start with 'This insane discovery changes everything we thought we knew about history...' in Scene 1.",
    "Banned Facts": "Start with 'These are the banned facts they tried to hide from us...' in Scene 1."
}

# Helpers
def get_video_dimensions(path):
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", 
            "-of", "csv=s=x:p=0", 
            path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts = res.stdout.strip().split('x')
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception as e:
        print(f"Error checking video dimensions: {e}")
    return 576, 1024

def has_audio_stream(path):
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-select_streams", "a:0", 
            "-show_entries", "stream=index", 
            "-of", "csv=p=0", 
            path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return len(res.stdout.strip()) > 0
    except Exception:
        return False

def download_file(url, folder, prefix):
    if not url or not url.strip().startswith(("http://", "https://")):
        return None
    url = url.strip()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        os.makedirs(folder, exist_ok=True)
        ext = url.split('.')[-1].split('?')[0]
        if len(ext) > 4 or not ext.isalnum():
            ext = "mp4"
        out_path = os.path.abspath(os.path.join(folder, f"{prefix}_{int(time.time())}.{ext}"))
        response = requests.get(url, headers=headers, stream=True, timeout=45)
        if response.status_code == 200:
            with open(out_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
    except Exception as e:
        print(f"Error downloading file {url}: {e}")
    return None

def download_music_preset(preset_name):
    if preset_name not in MUSIC_PRESETS:
        return None
    target_path = os.path.abspath(os.path.join("assets", "music", f"{preset_name.lower()}.mp3"))
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return target_path
    return download_file(MUSIC_PRESETS[preset_name], os.path.join("assets", "music"), preset_name.lower())

def download_satisfying_preset(preset_name):
    if preset_name not in SATISFYING_PRESETS:
        return None
    target_path = os.path.abspath(os.path.join("assets", "satisfying", f"{preset_name.lower().replace(' ', '_')}.mp4"))
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return target_path
    return download_file(SATISFYING_PRESETS[preset_name], os.path.join("assets", "satisfying"), preset_name.lower().replace(' ', '_'))

def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_ass_subtitles(storyboard, output_path, font_name="Arial", font_size=42, margin_v=150, alignment=2, highlight_color="&H00FFFF&"):
    """
    Generate an ASS subtitle file with sliding window word highlights.
    alignment 2 is Centered Bottom.
    """
    lines = [
        "[Script Info]",
        "Title: Viral Subtitles",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},&HFFFFFF,{highlight_color},&H000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,{alignment},50,50,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    cumulative_time = 0.0
    for scene in storyboard:
        text = scene.get("narration", "").strip()
        duration = scene.get("duration", 0.0)
        
        words = text.split()
        if not words:
            cumulative_time += duration
            continue
            
        total_chars = sum(len(w) for w in words)
        if total_chars == 0:
            cumulative_time += duration
            continue
            
        # Word durations proportional to length
        word_durations = [duration * (len(w) / total_chars) for w in words]
        
        # Word absolute timestamps
        times = []
        current_time = cumulative_time
        for d in word_durations:
            times.append((current_time, current_time + d))
            current_time += d
            
        # Group into chunks of 3 words
        words_per_chunk = 3
        for i in range(0, len(words), words_per_chunk):
            chunk_words = words[i:i+words_per_chunk]
            chunk_times = times[i:i+words_per_chunk]
            
            # For each word in this chunk, create a dialogue event where that word is highlighted
            for w_idx in range(len(chunk_words)):
                word_start = chunk_times[w_idx][0]
                word_end = chunk_times[w_idx][1]
                
                start_str = format_ass_time(word_start)
                end_str = format_ass_time(word_end)
                
                line_words = []
                for j, word in enumerate(chunk_words):
                    if j == w_idx:
                        # Highlight active word in selected color with bold
                        line_words.append(f"{{\c{highlight_color}\b1}}{word}{{\b0\c&HFFFFFF&}}")
                    else:
                        line_words.append(word)
                line_text = " ".join(line_words)
                lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{line_text}")
                
        cumulative_time += duration
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True

# Core Pipeline Functions
def generate_ollama_script(prompt: str, model: str, hook_style: str = "None (Direct Prompt)"):
    url = f"{OLLAMA_HOST}/api/generate"
    
    hook_instruction = VIRAL_HOOKS.get(hook_style, "")
    
    system_prompt = (
        "You are an expert viral TikTok, YouTube Shorts, and Instagram Reels writer. "
        "Your task is to generate a highly engaging 15-second script about the requested topic, "
        "broken down into exactly 5 sequential scenes. "
        "Respond ONLY with a valid JSON object matching this exact format, with no markdown styling, no conversational filler, and no extra text:\n"
        "{\n"
        "  \"topic\": \"Engaging vertical title of the video\",\n"
        "  \"background_music_style\": \"Cinematic\",\n"
        "  \"scenes\": [\n"
        "    {\n"
        "      \"narration\": \"A short engaging narrator sentence (approx. 7-8 words).\",\n"
        "      \"visual_prompt\": \"Detailed photorealistic 9:16 portrait/vertical scene description for Leonardo.ai to generate a background visual. Do not include camera frames or devices in the prompt.\"\n"
        "    },\n"
        "    ... (exactly 5 scenes)\n"
        "  ]\n"
        "}"
    )
    
    full_prompt = f"System: {system_prompt}\nUser: Write a viral 15-second script for: {prompt}."
    if hook_instruction:
        full_prompt += f" Hook Instruction: {hook_instruction}"
        
    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=45)
        if response.status_code == 200:
            resp_text = response.json().get("response", "").strip()
            data = json.loads(resp_text)
            if "scenes" in data and len(data["scenes"]) == 5:
                return data
    except Exception as e:
        print(f"Ollama JSON script generation failed: {e}")
        
    # Fallback script
    return {
        "topic": prompt if prompt else "Incredible Facts",
        "background_music_style": "Cinematic",
        "scenes": [
            {"narration": f"Here is an incredible fact about {prompt or 'our world'}.", "visual_prompt": f"Realistic vertical 9:16 portrait representing {prompt or 'discovery and mystery'}, cinematic lighting"},
            {"narration": "Scientists were completely shocked when they discovered this secret.", "visual_prompt": "Close-up expression of awe and disbelief, portrait view, dark modern lab background"},
            {"narration": "It changes everything we thought we knew about history.", "visual_prompt": "Beautiful ancient ruins under a celestial night sky, glowing dust particles, 9:16 view"},
            {"narration": "The implications could reshape our entire future.", "visual_prompt": "Futuristic skyline of a green sustainable city, vertical view, golden hour, 8k"},
            {"narration": "Follow for more mind-blowing facts every single day!", "visual_prompt": "Glowing neon holographic follow button on a dark studio wall, 9:16 view"}
        ]
    }

def generate_speech_audio(text: str, voice_key: str, speed: float = 1.0, effect: str = "Normal"):
    onnx_path = os.path.abspath(os.path.join("models", "kokoro-v1.0.onnx"))
    voices_path = os.path.abspath(os.path.join("models", "voices-v1.0.bin"))
    
    if not os.path.exists(onnx_path) or not os.path.exists(voices_path):
        return None, "Error: Kokoro model files not found in models/ directory."
        
    voice = KOKORO_VOICES.get(voice_key, "af_sarah")
    
    try:
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(onnx_path, voices_path)
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        
        raw_output_path = os.path.abspath(os.path.join("temp", f"voice_raw_{int(time.time())}.wav"))
        sf.write(raw_output_path, samples, sample_rate)
        
        if effect == "Kid (High Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_kid_{int(time.time())}.wav"))
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", raw_output_path, "-af", "asetrate=24000*1.3,atempo=1/1.3", pitch_output_path]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return pitch_output_path, "Success"
            
        elif effect == "Deep (Low Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_deep_{int(time.time())}.wav"))
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", raw_output_path, "-af", "asetrate=24000*0.82,atempo=1/0.82", pitch_output_path]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return pitch_output_path, "Success"
            
        return raw_output_path, "Success"
    except Exception as e:
        return None, f"Error: {e}"

def generate_leonardo_image(prompt: str, model_key: str, aspect_ratio: str):
    if not LEONARDO_API_KEY:
        return None
    model_id = LEONARDO_MODELS.get(model_key, "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3")
    width, height = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (576, 1024))
    
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEONARDO_API_KEY}"
    }
    payload = {
        "prompt": prompt,
        "num_images": 1,
        "width": width,
        "height": height,
        "modelId": model_id
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            generation_id = response.json().get("sdGenerationJob", {}).get("generationId")
            poll_url = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"
            
            for _ in range(30):
                time.sleep(2)
                poll_resp = requests.get(poll_url, headers=headers, timeout=10)
                if poll_resp.status_code == 200:
                    gen_data = poll_resp.json().get("generations_by_pk", {})
                    if gen_data.get("status") == "COMPLETE":
                        images = gen_data.get("generated_images", [])
                        if images:
                            image_url = images[0].get("url")
                            image_id = images[0].get("id")
                            img_data = requests.get(image_url).content
                            out_path = os.path.abspath(os.path.join("temp", f"scene_{int(time.time())}_{image_id[:8]}.png"))
                            with open(out_path, "wb") as f:
                                f.write(img_data)
                            return out_path, image_id
                    elif gen_data.get("status") == "FAILED":
                        break
    except Exception as e:
        print(f"Leonardo error: {e}")
    return None, None

def generate_leonardo_motion(image_id: str, prompt: str):
    if not LEONARDO_API_KEY or not image_id:
        return None
    url = "https://cloud.leonardo.ai/api/rest/v1/generations-image-to-video"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEONARDO_API_KEY}"
    }
    payload = {
        "imageId": image_id,
        "imageType": "GENERATED",
        "prompt": prompt,
        "model": "MOTION2",
        "isPublic": False
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            generation_id = response.json().get("motionGenerationJob", {}).get("generationId")
            poll_url = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"
            for _ in range(45):
                time.sleep(4)
                poll_resp = requests.get(poll_url, headers=headers, timeout=10)
                if poll_resp.status_code == 200:
                    gen_data = poll_resp.json().get("generations_by_pk", {})
                    if gen_data.get("status") == "COMPLETE":
                        videos = gen_data.get("generated_images", [])
                        if videos:
                            video_url = videos[0].get("url")
                            vid_data = requests.get(video_url).content
                            out_path = os.path.abspath(os.path.join("temp", f"motion_{int(time.time())}.mp4"))
                            with open(out_path, "wb") as f:
                                f.write(vid_data)
                            return out_path
                    elif gen_data.get("status") == "FAILED":
                        break
    except Exception as e:
        print(f"Motion error: {e}")
    return None

def composite_videos(b_roll_path, presenter_path, layout, output_path):
    if not os.path.exists(presenter_path):
        return False, "Presenter video not found."
    if not b_roll_path or not os.path.exists(b_roll_path):
        return False, "B-Roll video not found."

    w, h = get_video_dimensions(presenter_path)
    half_h = h // 2
    pip_w = w // 3
    if pip_w % 2 != 0:
        pip_w += 1
    pip_h = int(h * (pip_w / w))
    if pip_h % 2 != 0:
        pip_h += 1

    if layout == "Split-Screen (Top B-Roll, Bottom Presenter)":
        filter_complex = (
            f"[0:v]scale={w}:{half_h}:force_original_aspect_ratio=increase,crop={w}:{half_h}[top]; "
            f"[1:v]scale={w}:{half_h}:force_original_aspect_ratio=increase,crop={w}:{half_h}[bottom]; "
            f"[top][bottom]vstack=inputs=2[v]"
        )
    elif layout == "Picture-in-Picture (Presenter Bottom Right)":
        filter_complex = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg]; "
            f"[1:v]scale={pip_w}:{pip_h}:force_original_aspect_ratio=increase,crop={pip_w}:{pip_h}[fg]; "
            f"[bg][fg]overlay=main_w-overlay_w-20:main_h-overlay_h-20[v]"
        )
    elif layout == "Green Screen (Chroma Key Presenter on B-Roll)":
        filter_complex = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg]; "
            f"[1:v]chromakey=0x00FF00:0.15:0.2[fg_keyed]; "
            f"[bg][fg_keyed]overlay=x=0:y=0[v]"
        )
    else:
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", presenter_path, "-c:v", "copy", "-c:a", "copy", output_path]
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        return (res.returncode == 0), "Copy presenter only"

    audio_map = ["-map", "1:a"] if has_audio_stream(presenter_path) else []
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", b_roll_path, "-i", presenter_path,
        "-filter_complex", filter_complex, "-map", "[v]"
    ] + audio_map + [
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path
    ]
    try:
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        return (res.returncode == 0), res.stderr or res.stdout
    except Exception as e:
        return False, str(e)

# REST API Types
class ScriptRequest(BaseModel):
    prompt: str
    model: str
    hook_style: str = "None (Direct Prompt)"

class SpeechRequest(BaseModel):
    text: str
    voice: str
    speed: float = 1.0
    effect: str = "Normal"

class PresenterRequest(BaseModel):
    prompt: str
    model: str
    aspect_ratio: str = "9:16"

class LipsyncRequest(BaseModel):
    image_path: str
    audio_path: str
    quality: str = "Enhanced"
    wav2lip_version: str = "Wav2Lip_GAN"
    nosmooth: bool = True
    padding_u: int = 0
    padding_d: int = 10
    padding_l: int = 0
    padding_r: int = 0
    b_roll_url: Optional[str] = None
    layout: str = "None (Presenter Only)"

class ShortRequest(BaseModel):
    prompt: str
    model: str
    hook_style: str = "None (Direct Prompt)"
    visual_mode: str = "Cinematic Slideshow"  # Cinematic Slideshow or Leonardo Motion Video
    leonardo_model: str = "Lucid Realism (High Quality Face)"
    voice: str = "Sarah (Female - US - Soft)"
    speed: float = 1.0
    music_style: str = "Cinematic"
    satisfying_background: str = "None"  # None, Slime ASMR, Kinetic Sand, Satisfying Liquid
    enable_captions: bool = True
    caption_font: str = "Arial"
    caption_size: int = 42
    caption_margin_v: int = 150
    caption_color: str = "&H00FFFF&"

def get_ollama_models():
    """Dynamically fetch available models from local Ollama service."""
    ollama_models = []
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if r.status_code == 200:
            ollama_models = [m['name'] for m in r.json().get("models", [])]
    except Exception:
        pass
    if not ollama_models:
        ollama_models = ["deepseek-v4-pro:cloud", "gemma4:31b-cloud", "qwen3.5:0.8b", "gpt-oss:120b-cloud"]
    return ollama_models

# API Endpoints
@app.get("/api/config")
def get_config():
    ollama_models = get_ollama_models()

    return {
        "voices": list(KOKORO_VOICES.keys()),
        "leonardo_models": list(LEONARDO_MODELS.keys()),
        "aspect_ratios": list(ASPECT_RATIO_DIMENSIONS.keys()),
        "music_presets": ["None"] + list(MUSIC_PRESETS.keys()),
        "satisfying_presets": ["None"] + list(SATISFYING_PRESETS.keys()),
        "viral_hooks": list(VIRAL_HOOKS.keys()),
        "ollama_models": ollama_models
    }

@app.post("/api/generate-script")
def api_generate_script(req: ScriptRequest):
    return generate_ollama_script(req.prompt, req.model, req.hook_style)

@app.post("/api/generate-speech")
def api_generate_speech(req: SpeechRequest):
    path, msg = generate_speech_audio(req.text, req.voice, req.speed, req.effect)
    if not path:
        raise HTTPException(status_code=500, detail=msg)
    
    # Return relative URL path
    rel_path = os.path.relpath(path, os.path.abspath(os.path.curdir))
    return {"path": path, "url": f"http://localhost:8000/{rel_path.replace(os.path.sep, '/')}"}

@app.post("/api/generate-presenter")
def api_generate_presenter(req: PresenterRequest):
    path, image_id = generate_leonardo_image(req.prompt, req.model, req.aspect_ratio)
    if not path:
        raise HTTPException(status_code=500, detail="Image generation failed.")
    
    rel_path = os.path.relpath(path, os.path.abspath(os.path.curdir))
    return {"path": path, "url": f"http://localhost:8000/{rel_path.replace(os.path.sep, '/')}", "image_id": image_id}

@app.post("/api/run-lipsync")
def api_run_lipsync(req: LipsyncRequest):
    if not req.image_path or not os.path.exists(req.image_path):
        raise HTTPException(status_code=400, detail="Presenter image path not found.")
    if not req.audio_path or not os.path.exists(req.audio_path):
        raise HTTPException(status_code=400, detail="Audio file path not found.")
        
    try:
        b_roll_path = None
        if req.b_roll_url:
            b_roll_path = download_file(req.b_roll_url, "temp", "broll")

        info = sf.info(req.audio_path)
        duration = info.duration
        
        temp_video = os.path.abspath(os.path.join("temp", f"looped_input_{int(time.time())}.mp4"))
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", req.image_path, "-t", str(duration), "-r", "25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", temp_video
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Write config for Easy-Wav2Lip
        config = configparser.ConfigParser()
        config['OPTIONS'] = {
            'video_file': temp_video,
            'vocal_file': req.audio_path,
            'quality': req.quality,
            'output_height': 'full resolution',
            'wav2lip_version': req.wav2lip_version,
            'use_previous_tracking_data': 'True',
            'nosmooth': str(req.nosmooth),
            'preview_window': 'Full'
        }
        config['PADDING'] = {'u': str(req.padding_u), 'd': str(req.padding_d), 'l': str(req.padding_l), 'r': str(req.padding_r)}
        config['MASK'] = {'size': '2.5', 'feathering': '2', 'mouth_tracking': 'False', 'debug_mask': 'False'}
        config['OTHER'] = {'batch_process': 'False', 'output_suffix': '_Easy-Wav2Lip', 'include_settings_in_suffix': 'False', 'preview_settings': 'False', 'frame_to_preview': '100'}
        
        with open(os.path.join("Easy-Wav2Lip", "config.ini"), 'w') as f:
            config.write(f)
            
        final_video_path = os.path.abspath(os.path.join("temp", f"output_{int(time.time())}.mp4"))
        wav2lip_cmd = [sys.executable, "run.py", "-video_file", temp_video, "-vocal_file", req.audio_path, "-output_file", final_video_path]
        
        result = subprocess.run(wav2lip_cmd, cwd="Easy-Wav2Lip", capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Lipsync failed: {result.stderr or result.stdout}")
            
        out_path = final_video_path
        if req.layout != "None (Presenter Only)" and b_roll_path:
            composite_path = os.path.abspath(os.path.join("temp", f"composite_{int(time.time())}.mp4"))
            success, msg = composite_videos(b_roll_path, final_video_path, req.layout, composite_path)
            if success:
                out_path = composite_path
                
        rel_path = os.path.relpath(out_path, os.path.abspath(os.path.curdir))
        return {"path": out_path, "url": f"http://localhost:8000/{rel_path.replace(os.path.sep, '/')}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_viral_shorts_pipeline_new(
    prompt: str,
    model: str,
    hook_style: str = "None (Direct Prompt)",
    visual_mode: str = "Cinematic Slideshow",
    leonardo_model: str = "Lucid Realism (High Quality Face)",
    voice: str = "Sarah (Female - US - Soft)",
    speed: float = 1.0,
    music_style: str = "Cinematic",
    satisfying_background: str = "None",
    enable_captions: bool = True,
    caption_font: str = "Arial",
    caption_size: int = 42,
    caption_margin_v: int = 150,
    caption_color: str = "&H00FFFF&"
):
    """
    Core automated multi-scene viral shorts pipeline.
    """
    # 1. Script
    script_data = generate_ollama_script(prompt, model, hook_style)
    scenes = script_data.get("scenes", [])
    
    bg_music_path = download_music_preset(music_style) if music_style != "None" else None
    
    scene_videos = []
    scene_audios = []
    storyboard = []
    
    for idx, scene in enumerate(scenes):
        sc_text = scene["narration"]
        sc_visual_prompt = scene["visual_prompt"]
        
        # Synthesize voice
        sc_audio, err = generate_speech_audio(sc_text, voice, speed, "Normal")
        if not sc_audio:
            raise Exception(f"Voice synthesis failed at scene {idx+1}: {err}")
            
        info = sf.info(sc_audio)
        sc_duration = info.duration
        scene_audios.append(sc_audio)
        
        # Generate Image
        sc_img, image_id = generate_leonardo_image(sc_visual_prompt, leonardo_model, "9:16")
        if not sc_img:
            raise Exception(f"Image generation failed at scene {idx+1}")
            
        scene_video_path = os.path.abspath(os.path.join("temp", f"scene_vid_{int(time.time())}_{idx}.mp4"))
        
        # Make video segment (slideshow with zoompan or motion video)
        motion_vid_path = None
        if visual_mode == "Leonardo Motion Video" and image_id:
            motion_vid_path = generate_leonardo_motion(image_id, sc_visual_prompt)
            
        if motion_vid_path:
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", motion_vid_path, "-t", str(sc_duration),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", scene_video_path
            ]
        else:
            # Cinematic Slideshow (Ken Burns zoompan)
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", sc_img, "-t", str(sc_duration), "-r", "25",
                "-vf", f"scale=1920:3412,zoompan=z='min(zoom+0.001,1.3)':d={int(sc_duration*25)}:x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':s=1080x1920",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", scene_video_path
            ]
            
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        scene_videos.append(scene_video_path)
        
        img_rel = os.path.relpath(sc_img, os.path.abspath(os.path.curdir))
        aud_rel = os.path.relpath(sc_audio, os.path.abspath(os.path.curdir))
        storyboard.append({
            "scene": idx + 1,
            "narration": sc_text,
            "image_url": f"http://localhost:8000/{img_rel.replace(os.path.sep, '/')}",
            "audio_url": f"http://localhost:8000/{aud_rel.replace(os.path.sep, '/')}",
            "duration": sc_duration
        })
        
    # Concatenate segments
    timestamp = int(time.time())
    merged_video = os.path.abspath(os.path.join("temp", f"merged_video_{timestamp}.mp4"))
    merged_audio = os.path.abspath(os.path.join("temp", f"merged_audio_{timestamp}.wav"))
    
    video_list_path = os.path.abspath(os.path.join("temp", f"video_list_{timestamp}.txt"))
    audio_list_path = os.path.abspath(os.path.join("temp", f"audio_list_{timestamp}.txt"))
    
    with open(video_list_path, "w") as vf:
        for p in scene_videos:
            vf.write(f"file '{p}'\n")
    with open(audio_list_path, "w") as af:
        for p in scene_audios:
            af.write(f"file '{p}'\n")
            
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", video_list_path, "-c", "copy", merged_video], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_list_path, "-c", "copy", merged_audio], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        os.remove(video_list_path)
        os.remove(audio_list_path)
    except Exception:
        pass
        
    # Mix Audio (Speech + BG Music)
    audio_mixed = os.path.abspath(os.path.join("temp", f"audio_mixed_{timestamp}.wav"))
    if bg_music_path and os.path.exists(bg_music_path):
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_audio, "-stream_loop", "-1", "-i", bg_music_path,
            "-filter_complex", "[1:a]volume=0.15[bgm]; [0:a][bgm]amix=inputs=2:duration=first[a]",
            "-map", "[a]", "-c:a", "pcm_s16le", audio_mixed
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.copy(merged_audio, audio_mixed)
        
    # Composite Video with Satisfying Split-screen (if selected)
    satisfying_path = None
    if satisfying_background != "None":
        satisfying_path = download_satisfying_preset(satisfying_background)
        
    processed_video = os.path.abspath(os.path.join("temp", f"processed_video_{timestamp}.mp4"))
    if satisfying_path and os.path.exists(satisfying_path):
        # Split-Screen layout: scale both to 1080x960 and stack vertically
        filter_complex = (
            f"[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top]; "
            f"[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom]; "
            f"[top][bottom]vstack=inputs=2[v]"
        )
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_video, "-stream_loop", "-1", "-i", satisfying_path,
            "-i", audio_mixed, "-filter_complex", filter_complex, "-map", "[v]", "-map", "2:a",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", processed_video
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Just merge video and mixed audio
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_video, "-i", audio_mixed, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", processed_video
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    # Burn Subtitles
    final_rendered_video = os.path.abspath(os.path.join("outputs", f"viral_reel_{timestamp}.mp4"))
    if enable_captions:
        ass_path = os.path.abspath(os.path.join("temp", f"subtitles_{timestamp}.ass"))
        # Alignment 2 is Centered Bottom
        align = 2
        generate_ass_subtitles(
            storyboard, ass_path, caption_font, caption_size,
            margin_v=caption_margin_v, alignment=align, highlight_color=caption_color
        )
        
        # Compile with subtitles
        sub_filter = f"subtitles='temp/subtitles_{timestamp}.ass'"
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", processed_video, "-vf", sub_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", final_rendered_video
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.copy(processed_video, final_rendered_video)
        
    return final_rendered_video, storyboard, script_data.get("topic", prompt)


@app.post("/api/generate-short")
def api_generate_short(req: ShortRequest):
    """
    Complete automated multi-scene viral shorts pipeline endpoint.
    """
    try:
        final_video, storyboard, topic = run_viral_shorts_pipeline_new(
            prompt=req.prompt,
            model=req.model,
            hook_style=req.hook_style,
            visual_mode=req.visual_mode,
            leonardo_model=req.leonardo_model,
            voice=req.voice,
            speed=req.speed,
            music_style=req.music_style,
            satisfying_background=req.satisfying_background,
            enable_captions=req.enable_captions,
            caption_font=req.caption_font,
            caption_size=req.caption_size,
            caption_margin_v=req.caption_margin_v,
            caption_color=req.caption_color
        )
        rel_out = os.path.relpath(final_video, os.path.abspath(os.path.curdir))
        return {
            "success": True,
            "video_url": f"http://localhost:8000/{rel_out.replace(os.path.sep, '/')}",
            "storyboard": storyboard,
            "topic": topic
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
