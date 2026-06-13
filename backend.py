import os
import sys
import time
import json
import uuid
import requests
import configparser
import subprocess
import soundfile as sf
import shutil
import threading
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Custom imports for search and uploads
import db_manager
from search_helper import get_web_grounding_context, clean_json_response
from uploader_youtube import upload_video_to_youtube, is_youtube_authenticated, trigger_youtube_auth_flow_url
from uploader_instagram import upload_reel_to_instagram, is_instagram_configured

# Global in-memory storage for upload job logs
upload_jobs = {}

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

def map_speaker_to_voice_key(speaker_name: str) -> str:
    """Map a character or speaker name to the full key in KOKORO_VOICES."""
    if not speaker_name:
        return "Sarah (Female - US - Soft)"
    speaker_clean = speaker_name.split('(')[0].strip().lower()
    for display_name in KOKORO_VOICES:
        display_clean = display_name.split('(')[0].strip().lower()
        if speaker_clean in display_clean or display_clean in speaker_clean:
            return display_name
    return "Sarah (Female - US - Soft)"

def mix_transition_sfx(main_audio_path, output_audio_path, transition_times):
    """Mix synthesized transition whoosh sound effects at scene boundary timestamps."""
    whoosh_path = os.path.abspath(os.path.join("assets", "sfx", "whoosh.wav"))
    if not os.path.exists(whoosh_path) or not transition_times:
        shutil.copy(main_audio_path, output_audio_path)
        return
        
    ffmpeg_cmd = ["ffmpeg", "-y", "-i", main_audio_path]
    for _ in transition_times:
        ffmpeg_cmd += ["-i", whoosh_path]
        
    inputs = ["[0:a]"]
    filter_parts = []
    
    for idx, t_sec in enumerate(transition_times):
        t_ms = int(t_sec * 1000)
        sfx_label = f"[whoosh{idx}]"
        filter_parts.append(f"[{idx+1}:a]adelay={t_ms}|{t_ms}[whoosh_del{idx}]; [whoosh_del{idx}]volume=0.20{sfx_label}")
        inputs.append(sfx_label)
        
    amix_in = "".join(inputs)
    filter_parts.append(f"{amix_in}amix=inputs={len(inputs)}:duration=first[aout]")
    
    ffmpeg_cmd += [
        "-filter_complex", "; ".join(filter_parts),
        "-map", "[aout]", "-c:a", "pcm_s16le", output_audio_path
    ]
    
    try:
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error mixing transition SFX: {e}")
        shutil.copy(main_audio_path, output_audio_path)

def generate_ass_subtitles(storyboard, output_path, font_name="Arial", font_size=42, margin_v=150, alignment=2, highlight_color="&H00FFFF&", style_mode="Viral Pop"):
    """
    Generate an ASS subtitle file with sliding window word highlights or animated central pops.
    """
    if style_mode == "Viral Pop":
        # Centered, larger, yellow/green highlights, thick outline for MrBeast/Hormozi style
        style_line = f"Style: Default,{font_name},{font_size + 15},&HFFFFFF,{highlight_color},&H000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,2,{alignment},50,50,{margin_v},1"
    else:
        # Standard centered bottom style
        style_line = f"Style: Default,{font_name},{font_size},&HFFFFFF,{highlight_color},&H000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,{alignment},50,50,{margin_v},1"

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
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    # 80ms zoom up to 120%, 70ms decay back to 100%
    anim_tags = r"{\fscx80\fscy80\t(0,80,\fscx120\fscy120)\t(80,150,\fscx100\fscy100)}"
    
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
            
        # Group into chunks
        words_per_chunk = 3
        
        for i in range(0, len(words), words_per_chunk):
            chunk_words = words[i:i+words_per_chunk]
            chunk_times = times[i:i+words_per_chunk]
            
            for w_idx in range(len(chunk_words)):
                word_start = chunk_times[w_idx][0]
                word_end = chunk_times[w_idx][1]
                
                start_str = format_ass_time(word_start)
                end_str = format_ass_time(word_end)
                
                line_words = []
                for j, word in enumerate(chunk_words):
                    if j == w_idx:
                        # Highlight active word
                        line_words.append(f"{{\c{highlight_color}\b1}}{word}{{\b0\c&HFFFFFF&}}")
                    else:
                        line_words.append(word)
                        
                line_text = " ".join(line_words)
                # Set style properties and pop animation
                if style_mode == "Viral Pop":
                    if w_idx == 0:
                        # Pop the entire line on chunk entrance
                        line_text = f"{anim_tags}{{\b1\c&HFFFFFF&}}{line_text}"
                    else:
                        # Render static line for subsequent words to prevent jitter
                        line_text = f"{{\b1\c&HFFFFFF&\fscx100\fscy100}}{line_text}"
                else:
                    line_text = f"{{\c&HFFFFFF&}}{line_text}"
                    
                lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{line_text}")
                
        cumulative_time += duration
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True

# Core Pipeline Functions
def generate_ollama_script(prompt: str, model: str, hook_style: str = "None (Direct Prompt)", enable_search: bool = False):
    url = f"{OLLAMA_HOST}/api/generate"
    
    hook_instruction = VIRAL_HOOKS.get(hook_style, "")
    
    # 1. Handle dynamic web search fact checking
    grounding_info = ""
    if enable_search:
        try:
            grounding_data = get_web_grounding_context(prompt, model)
            if grounding_data.get("requires_search") and grounding_data.get("context"):
                grounding_info = f"\nVERIFIED INTERNET SEARCH FACTS:\n{grounding_data['context']}\n"
                print(f"RAG Grounding: Query used: '{grounding_data['search_query']}'. Injected search context successfully.")
        except Exception as e:
            print(f"Failed to perform web search grounding: {e}")
            
    # Stage 1: Creative Story / Script Writer (Free-form text)
    storyteller_system = (
        "You are an expert creative storyteller and copywriter. "
        "Your task is to write a highly engaging, viral 15-second story or script based on the topic. "
        "It must flow naturally as a single narrative and keep the listener hooked from the first second. "
        "Keep the total length to approximately 35-45 words. "
        "Do not include scene numbers, brackets, or speaker names in this text—only write the raw narrative story text."
    )
    
    storyteller_prompt = f"System: {storyteller_system}\n{grounding_info}\nUser: Write a 15-second viral story about: {prompt}."
    if hook_instruction:
        storyteller_prompt += f" Hook Instruction: {hook_instruction}"
        
    story_text = ""
    try:
        payload1 = {
            "model": model,
            "prompt": storyteller_prompt,
            "stream": False
        }
        response1 = requests.post(url, json=payload1, timeout=45)
        if response1.status_code == 200:
            story_text = response1.json().get("response", "").strip()
            print(f"--- Generated Cohesive Story ---\n{story_text}\n---------------------------------")
    except Exception as e:
        print(f"Ollama story text generation failed: {e}")
        
    if not story_text:
        story_text = prompt
        
    # Stage 2: Storyboarder & Scene Segmenter (Strict JSON)
    storyboarder_system = (
        "You are an expert storyboarder. Take the provided story text and split it into exactly 5 sequential scenes. "
        "To ensure visual continuity and keep the focus point consistent (so the video does not look like a series of unrelated random images), you MUST define:\n"
        "1. A 'global_visual_style' representing the overall visual medium, art style, camera/lighting style, and color palette (e.g. 'cinematic 3D render, dark mood, neon green accents, highly detailed, 8k').\n"
        "2. A 'global_subject_focus' describing the main character, subject, or object that remains constant across the entire story (e.g. 'a futuristic female astronaut wearing a white helmet with a gold visor').\n"
        "For each scene:\n"
        "1. Extract the exact segment of narration text from the story (usually 1 short sentence, approx. 7-8 words).\n"
        "2. Assign a speaker name from this list: Sarah, Bella, Nicole, Sky, Alloy, Kore, River, Adam, Michael, Fenrir, Puck, Echo, Liam, Onyx, Emma, Isabella, George, Lewis.\n"
        "3. Write a scene-specific action/setting description for 'visual_prompt'. This should describe ONLY the specific action, movement, or background setting of that scene, designed to be combined with the global style and subject description. Do not include camera frames, phone frames, or device frames in this prompt.\n\n"
        "Respond ONLY with a valid JSON object matching this exact format, with no markdown styling, no conversational filler, and no extra text:\n"
        "{\n"
        "  \"topic\": \"Engaging vertical title of the video\",\n"
        "  \"background_music_style\": \"Cinematic\",\n"
        "  \"global_visual_style\": \"Overall art style, camera/lighting, and palette description\",\n"
        "  \"global_subject_focus\": \"Description of the main character/object focus point\",\n"
        "  \"scenes\": [\n"
        "    {\n"
        "      \"speaker\": \"Speaker Name (e.g. Sarah)\",\n"
        "      \"narration\": \"Exact segment of narration text from the story.\",\n"
        "      \"visual_prompt\": \"Specific action, pose, or background setting representing the scene's narration.\"\n"
        "    },\n"
        "    ... (exactly 5 scenes)\n"
        "  ],\n"
        "  \"youtube_metadata\": {\n"
        "    \"title\": \"Catchy optimized YouTube Shorts title (max 100 chars)\",\n"
        "    \"description\": \"SEO-friendly description with relevant search keywords and tags\",\n"
        "    \"tags\": [\"shorts\", \"facts\", \"viral\"]\n"
        "  },\n"
        "  \"instagram_metadata\": {\n"
        "    \"caption\": \"Engaging Instagram Reels caption with emojis and hashtags\"\n"
        "  }\n"
        "}"
    )
    
    storyboarder_prompt = f"System: {storyboarder_system}\nStory to segment:\n{story_text}"
    
    payload2 = {
        "model": model,
        "prompt": storyboarder_prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        response2 = requests.post(url, json=payload2, timeout=45)
        if response2.status_code == 200:
            resp_text = response2.json().get("response", "").strip()
            cleaned = clean_json_response(resp_text)
            data = json.loads(cleaned)
            if "scenes" in data and len(data["scenes"]) == 5:
                return data
    except Exception as e:
        print(f"Ollama JSON storyboard generation failed: {e}")
        
    # Fallback script with metadata and speakers
    return {
        "topic": prompt if prompt else "Incredible Facts",
        "background_music_style": "Cinematic",
        "global_visual_style": "realistic vertical 9:16 portrait, cinematic lighting, dramatic mood, high-detail",
        "global_subject_focus": "a detailed mysterious mechanical box emitting faint golden light",
        "scenes": [
            {"speaker": "Sarah", "narration": f"Here is an incredible fact about {prompt or 'our world'}.", "visual_prompt": "resting on a dust-covered desk inside a dark ancient study room"},
            {"speaker": "Adam", "narration": "Scientists were completely shocked when they discovered this secret.", "visual_prompt": "slowly unlocking itself as gears slide outward"},
            {"speaker": "Sarah", "narration": "It changes everything we thought we knew about history.", "visual_prompt": "opening wide, revealing a small floating miniature galaxy inside"},
            {"speaker": "Adam", "narration": "The implications could reshape our entire future.", "visual_prompt": "projecting bright blue holographic stars onto the study walls"},
            {"speaker": "George", "narration": "Follow for more mind-blowing facts every single day!", "visual_prompt": "closing shut, leaving glowing golden sparks in the air"}
        ],
        "youtube_metadata": {
            "title": f"The Truth About {prompt or 'This Topic'}!",
            "description": f"Amazing facts and details about {prompt or 'this topic'}. #shorts #facts #viral",
            "tags": ["shorts", "facts", "viral", "interesting"]
        },
        "instagram_metadata": {
            "caption": f"Mind-blowing facts about {prompt or 'this concept'}! 🤯✨ #reels #explore #viral #facts"
        }
    }


def trim_audio_silence(input_path: str) -> str:
    """Trim silence from the start and end of a WAV file using FFmpeg."""
    if not input_path or not os.path.exists(input_path):
        return input_path
    trimmed_path = input_path.replace(".wav", "_trimmed.wav")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
        trimmed_path
    ]
    try:
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(trimmed_path) and os.path.getsize(trimmed_path) > 0:
            try:
                os.remove(input_path)
            except Exception:
                pass
            return trimmed_path
    except Exception as e:
        print(f"Error trimming audio silence: {e}")
    return input_path

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
        
        audio_path = raw_output_path
        if effect == "Kid (High Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_kid_{int(time.time())}.wav"))
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", raw_output_path, "-af", "asetrate=24000*1.3,atempo=1/1.3", pitch_output_path]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                os.remove(raw_output_path)
            except Exception:
                pass
            audio_path = pitch_output_path
            
        elif effect == "Deep (Low Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_deep_{int(time.time())}.wav"))
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", raw_output_path, "-af", "asetrate=24000*0.82,atempo=1/0.82", pitch_output_path]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                os.remove(raw_output_path)
            except Exception:
                pass
            audio_path = pitch_output_path
            
        trimmed_path = trim_audio_silence(audio_path)
        return trimmed_path, "Success"
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
    enable_search: bool = False

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
    enable_search: bool = False
    enable_transition_sfx: bool = True

class UploadRequest(BaseModel):
    video_path: str
    platforms: List[str]  # e.g. ["youtube", "instagram"]
    youtube_title: Optional[str] = ""
    youtube_description: Optional[str] = ""
    youtube_tags: Optional[List[str]] = []
    youtube_privacy: Optional[str] = "private"
    instagram_caption: Optional[str] = ""


def get_ollama_models():
    """Dynamically fetch available models from local Ollama service."""
    ollama_models = []
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if r.status_code == 200:
            ollama_models = [m['name'] for m in r.json().get("models", [])]
    except Exception:
        pass
    
    # Ensure minimax-m3:cloud is at the front of the list
    if "minimax-m3:cloud" in ollama_models:
        ollama_models.remove("minimax-m3:cloud")
    ollama_models.insert(0, "minimax-m3:cloud")
    
    # Add other fallbacks if not present
    for fallback in ["deepseek-v4-pro:cloud", "gemma4:31b-cloud", "qwen3.5:0.8b", "gpt-oss:120b-cloud"]:
        if fallback not in ollama_models:
            ollama_models.append(fallback)
            
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
    caption_color: str = "&H00FFFF&",
    enable_search: bool = False,
    caption_style: str = "Viral Pop",
    enable_transition_sfx: bool = True,
    custom_storyboard: Optional[List[dict]] = None,
    custom_script_data: Optional[dict] = None
):
    """
    Core automated multi-scene viral shorts pipeline.
    Supports rendering directly from custom storyboards and multi-voice configuration.
    """
    # 1. Script
    if custom_script_data:
        script_data = custom_script_data
        scenes = script_data.get("scenes", [])
    elif custom_storyboard:
        scenes = custom_storyboard
        script_data = {"scenes": scenes}
    else:
        script_data = generate_ollama_script(prompt, model, hook_style, enable_search=enable_search)
        scenes = script_data.get("scenes", [])
    
    bg_music_path = download_music_preset(music_style) if music_style != "None" else None
    
    scene_videos = []
    scene_audios = []
    storyboard = []
    
    for idx, scene in enumerate(scenes):
        sc_text = scene["narration"]
        sc_visual_prompt = scene["visual_prompt"]
        
        # Combine scene prompt with global visual style and subject if present
        global_style = script_data.get("global_visual_style", "") if script_data else ""
        global_subject = script_data.get("global_subject_focus", "") if script_data else ""
        combined_prompt_parts = []
        if global_subject:
            combined_prompt_parts.append(global_subject)
        combined_prompt_parts.append(sc_visual_prompt)
        if global_style:
            combined_prompt_parts.append(global_style)
        final_visual_prompt = ", ".join(combined_prompt_parts)
        
        # Pick speaker voice
        if not custom_storyboard and not custom_script_data:
            sc_voice_key = voice
        else:
            sc_speaker = scene.get("speaker", voice)
            sc_voice_key = map_speaker_to_voice_key(sc_speaker) if isinstance(sc_speaker, str) else voice
        
        # Synthesize voice if audio doesn't exist
        sc_audio = scene.get("audio_path")
        if not sc_audio or not os.path.exists(sc_audio):
            sc_audio, err = generate_speech_audio(sc_text, sc_voice_key, speed, "Normal")
            if not sc_audio:
                raise Exception(f"Voice synthesis failed at scene {idx+1}: {err}")
            
        info = sf.info(sc_audio)
        sc_duration = info.duration
        scene_audios.append(sc_audio)
        
        # Generate Image if not exists
        sc_img = scene.get("image_path")
        image_id = scene.get("image_id")
        if not sc_img or not os.path.exists(sc_img):
            sc_img, image_id = generate_leonardo_image(final_visual_prompt, leonardo_model, "9:16")
            if not sc_img:
                raise Exception(f"Image generation failed at scene {idx+1}")
            
        scene_video_path = os.path.abspath(os.path.join("temp", f"scene_vid_{int(time.time())}_{idx}.mp4"))
        
        # Make video segment (slideshow with zoompan or motion video)
        motion_vid_path = None
        if visual_mode == "Leonardo Motion Video" and image_id:
            motion_vid_path = generate_leonardo_motion(image_id, final_visual_prompt)
            
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
            "speaker": sc_speaker,
            "narration": sc_text,
            "visual_prompt": final_visual_prompt,
            "image_url": f"http://localhost:8000/{img_rel.replace(os.path.sep, '/')}",
            "image_path": sc_img,
            "image_id": image_id,
            "audio_url": f"http://localhost:8000/{aud_rel.replace(os.path.sep, '/')}",
            "audio_path": sc_audio,
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
        
    # Mix transition SFX into audio_mixed
    transition_times = []
    curr_t = 0.0
    for sc in storyboard[:-1]:
        curr_t += sc["duration"]
        transition_times.append(curr_t)
        
    audio_final_mixed = os.path.abspath(os.path.join("temp", f"audio_final_mixed_{timestamp}.wav"))
    if enable_transition_sfx:
        mix_transition_sfx(audio_mixed, audio_final_mixed, transition_times)
    else:
        shutil.copy(audio_mixed, audio_final_mixed)
        
    # Composite Video with Satisfying Split-screen (if selected)
    satisfying_path = None
    if satisfying_background != "None":
        satisfying_path = download_satisfying_preset(satisfying_background)
        
    processed_video = os.path.abspath(os.path.join("temp", f"processed_video_{timestamp}.mp4"))
    if satisfying_path and os.path.exists(satisfying_path):
        filter_complex = (
            f"[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top]; "
            f"[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom]; "
            f"[top][bottom]vstack=inputs=2[v]"
        )
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_video, "-stream_loop", "-1", "-i", satisfying_path,
            "-i", audio_final_mixed, "-filter_complex", filter_complex, "-map", "[v]", "-map", "2:a",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", processed_video
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_video, "-i", audio_final_mixed, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", processed_video
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    # Burn Subtitles
    final_rendered_video = os.path.abspath(os.path.join("outputs", f"viral_reel_{timestamp}.mp4"))
    if enable_captions:
        ass_path = os.path.abspath(os.path.join("temp", f"subtitles_{timestamp}.ass"))
        align = 2
        generate_ass_subtitles(
            storyboard, ass_path, caption_font, caption_size,
            margin_v=caption_margin_v, alignment=align, highlight_color=caption_color,
            style_mode=caption_style
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
        
    return final_rendered_video, storyboard, script_data.get("topic", prompt), script_data


# New Request Models & APIs
class DraftRequest(BaseModel):
    prompt: str
    model: str
    hook_style: str = "None (Direct Prompt)"
    enable_search: bool = False
    voice: Optional[str] = "Sarah (Female - US - Soft)"

class RenderRequest(BaseModel):
    generation_id: str
    storyboard: List[dict]
    visual_mode: str = "Cinematic Slideshow"
    leonardo_model: str = "Lucid Realism (High Quality Face)"
    voice: str = "Sarah (Female - US - Soft)"
    speed: float = 1.0
    music_style: str = "Cinematic"
    satisfying_background: str = "None"
    enable_captions: bool = True
    caption_font: str = "Arial"
    caption_size: int = 42
    caption_margin_v: int = 150
    caption_color: str = "&H00FFFF&"
    caption_style: str = "Viral Pop"  # 'Viral Pop' or 'Standard'
    enable_transition_sfx: bool = True

class SingleAssetRegenRequest(BaseModel):
    generation_id: str
    scene_index: int
    asset_type: str
    prompt: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = 1.0
    leonardo_model: Optional[str] = None

class DbUploadRequest(BaseModel):
    video_generation_id: str
    platforms: List[str]
    youtube_title: Optional[str] = ""
    youtube_description: Optional[str] = ""
    youtube_tags: Optional[List[str]] = []
    youtube_privacy: Optional[str] = "private"
    instagram_caption: Optional[str] = ""
    scheduled_time: Optional[str] = None

@app.post("/api/draft-script")
def api_draft_script(req: DraftRequest):
    try:
        gen_id = str(uuid.uuid4())
        script_data = generate_ollama_script(req.prompt, req.model, req.hook_style, enable_search=req.enable_search)
        scenes = script_data.get("scenes", [])
        
        # Build initial storyboard structure
        storyboard = []
        for idx, scene in enumerate(scenes):
            storyboard.append({
                "scene": idx + 1,
                "speaker": req.voice if req.voice else scene.get("speaker", "Sarah"),
                "narration": scene.get("narration", ""),
                "visual_prompt": scene.get("visual_prompt", ""),
                "image_url": "",
                "image_path": "",
                "audio_url": "",
                "audio_path": "",
                "duration": 0.0
            })
            
        db_manager.create_video_generation(
            gen_id, req.prompt, script_data.get("topic", req.prompt), script_data, storyboard, status="draft"
        )
        return {
            "success": True,
            "generation_id": gen_id,
            "topic": script_data.get("topic", req.prompt),
            "storyboard": storyboard,
            "youtube_metadata": script_data.get("youtube_metadata"),
            "instagram_metadata": script_data.get("instagram_metadata")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/regenerate-scene-asset")
def api_regenerate_scene_asset(req: SingleAssetRegenRequest):
    gen = db_manager.get_video_generation(req.generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Video generation not found")
        
    storyboard = gen["storyboard"]
    if req.scene_index < 0 or req.scene_index >= len(storyboard):
        raise HTTPException(status_code=400, detail="Invalid scene index")
        
    scene = storyboard[req.scene_index]
    
    try:
        if req.asset_type == "image":
            prompt = req.prompt or scene.get("visual_prompt")
            model = req.leonardo_model or "Lucid Realism (High Quality Face)"
            path, image_id = generate_leonardo_image(prompt, model, "9:16")
            if not path:
                raise ValueError("Leonardo image generation failed")
                
            rel_path = os.path.relpath(path, os.path.abspath(os.path.curdir))
            scene["image_path"] = path
            scene["image_url"] = f"http://localhost:8000/{rel_path.replace(os.path.sep, '/')}"
            scene["image_id"] = image_id
            scene["visual_prompt"] = prompt
            
        elif req.asset_type == "audio":
            text = req.prompt or scene.get("narration")
            voice = req.voice or scene.get("speaker", "Sarah")
            path, msg = generate_speech_audio(text, voice, req.speed or 1.0, "Normal")
            if not path:
                raise ValueError(f"Kokoro voice synthesis failed: {msg}")
                
            info = sf.info(path)
            duration = info.duration
            rel_path = os.path.relpath(path, os.path.abspath(os.path.curdir))
            scene["audio_path"] = path
            scene["audio_url"] = f"http://localhost:8000/{rel_path.replace(os.path.sep, '/')}"
            scene["duration"] = duration
            scene["narration"] = text
            scene["speaker"] = voice
            
        else:
            raise HTTPException(status_code=400, detail="Invalid asset type")
            
        db_manager.update_video_generation(req.generation_id, storyboard=storyboard)
        return {
            "success": True,
            "scene": scene
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_render_task(generation_id: str, req: RenderRequest):
    try:
        db_manager.update_video_generation(generation_id, status="rendering")
        
        final_video, storyboard, topic, script_data = run_viral_shorts_pipeline_new(
            prompt="",
            model="",
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
            caption_color=req.caption_color,
            caption_style=req.caption_style,
            enable_transition_sfx=req.enable_transition_sfx,
            custom_storyboard=req.storyboard
        )
        
        db_manager.update_video_generation(
            generation_id, storyboard=storyboard, final_video_path=final_video, status="completed"
        )
    except Exception as e:
        print(f"Rendering failed: {e}")
        db_manager.update_video_generation(generation_id, status="failed")

@app.post("/api/render-storyboard")
def api_render_storyboard(req: RenderRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_render_task, req.generation_id, req)
    return {"success": True, "generation_id": req.generation_id}

@app.post("/api/generate-short")
def api_generate_short(req: ShortRequest):
    """
    Automated pipeline endpoint. Logs the resulting video generation directly to DB.
    """
    try:
        gen_id = str(uuid.uuid4())
        # Log initial draft status
        db_manager.create_video_generation(gen_id, req.prompt, req.prompt, None, None, status="rendering")
        
        final_video, storyboard, topic, script_data = run_viral_shorts_pipeline_new(
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
            caption_color=req.caption_color,
            enable_search=req.enable_search,
            caption_style="Viral Pop",
            enable_transition_sfx=req.enable_transition_sfx
        )
        rel_out = os.path.relpath(final_video, os.path.abspath(os.path.curdir))
        
        db_manager.update_video_generation(
            gen_id, topic=topic, script_data=script_data, storyboard=storyboard, final_video_path=final_video, status="completed"
        )
        
        return {
            "success": True,
            "video_url": f"http://localhost:8000/{rel_out.replace(os.path.sep, '/')}",
            "storyboard": storyboard,
            "topic": topic,
            "youtube_metadata": script_data.get("youtube_metadata"),
            "instagram_metadata": script_data.get("instagram_metadata"),
            "generation_id": gen_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/youtube/auth-status")
def get_youtube_auth_status():
    return {"authenticated": is_youtube_authenticated()}

@app.get("/api/youtube/auth-init")
def init_youtube_auth():
    try:
        msg = trigger_youtube_auth_flow_url()
        return {"success": True, "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/instagram/auth-status")
def get_instagram_auth_status():
    return {"configured": is_instagram_configured()}

def process_upload_job(job_id: str):
    """Executes upload processes for direct API uploads (persisted in DB)."""
    job = db_manager.get_upload_job(job_id)
    if not job:
        print(f"Error: Job {job_id} not found in database.")
        return
        
    db_manager.update_upload_job(job_id, status="running", logs=job.get("logs", []) + ["Job started processing..."])
    logs = job.get("logs", []) + ["Job started processing..."]
    
    def log_message(msg):
        logs.append(msg)
        db_manager.update_upload_job(job_id, logs=logs)
        print(f"[Job {job_id}] {msg}")
        
    try:
        # Get final video path
        video_gen = db_manager.get_video_generation(job["video_generation_id"])
        if not video_gen or not video_gen.get("final_video_path"):
            # Check if video_path is passed directly in some legacy way
            raise ValueError("Associated video generation or final video file not found.")
            
        video_file = video_gen["final_video_path"]
        
        # Extract relative path from URL if a localhost URL was passed
        if video_file.startswith("http://") or video_file.startswith("https://"):
            parsed_path = video_file.split("localhost:8000/")[-1]
            from urllib.parse import unquote
            video_file = unquote(parsed_path)
            
        video_file = os.path.abspath(video_file)
        
        if not os.path.exists(video_file):
            raise FileNotFoundError(f"Video file not found locally at: {video_file}")
            
        if "youtube" in job["platforms"]:
            log_message("YouTube upload starting...")
            yt_meta = job.get("youtube_metadata") or {}
            
            def yt_progress(pct):
                if logs and logs[-1].startswith("YouTube upload progress:"):
                    logs[-1] = f"YouTube upload progress: {pct}%"
                else:
                    logs.append(f"YouTube upload progress: {pct}%")
                db_manager.update_upload_job(job_id, logs=logs)
                
            vid_id = upload_video_to_youtube(
                video_file,
                yt_meta.get("title", "AI Generated Short"),
                yt_meta.get("description", ""),
                yt_meta.get("tags", []),
                yt_meta.get("privacy", "private"),
                progress_callback=yt_progress
            )
            log_message(f"YouTube upload successful! Video URL: https://youtu.be/{vid_id}")
            
        if "instagram" in job["platforms"]:
            log_message("Instagram Reels upload starting...")
            ig_meta = job.get("instagram_metadata") or {}
            
            def ig_progress(msg):
                log_message(msg)
                
            media_id = upload_reel_to_instagram(
                video_file,
                ig_meta.get("caption", ""),
                progress_callback=ig_progress
            )
            log_message(f"Instagram upload successful! Media ID: {media_id}")
            
        log_message("Upload process complete!")
        db_manager.update_upload_job(job_id, status="completed", logs=logs)
    except Exception as e:
        log_message(f"Upload failed: {str(e)}")
        db_manager.update_upload_job(job_id, status="failed", logs=logs)

def upload_scheduler_loop():
    """Background polling thread for scheduled uploads."""
    print("Starting background upload scheduler thread...")
    while True:
        try:
            # Query db for scheduled jobs
            now_iso = datetime.utcnow().isoformat() + "Z"
            pending_jobs = db_manager.get_pending_scheduled_jobs(now_iso)
            for job in pending_jobs:
                job_id = job["id"]
                # Mark job as running and process in a separate thread
                db_manager.update_upload_job(job_id, status="running")
                t = threading.Thread(target=process_upload_job, args=(job_id,))
                t.daemon = True
                t.start()
        except Exception as e:
            print(f"Error in upload scheduler loop: {e}")
        time.sleep(10)

@app.on_event("startup")
def startup_event():
    scheduler_thread = threading.Thread(target=upload_scheduler_loop)
    scheduler_thread.daemon = True
    scheduler_thread.start()

@app.get("/api/history")
def api_get_history():
    rows = db_manager.list_video_generations()
    for row in rows:
        if row.get("final_video_path"):
            rel = os.path.relpath(row["final_video_path"], os.path.abspath(os.path.curdir))
            row["video_url"] = f"http://localhost:8000/{rel.replace(os.path.sep, '/')}"
        else:
            row["video_url"] = ""
    return rows

@app.get("/api/upload-queue")
def api_get_upload_queue():
    return db_manager.list_upload_jobs()

@app.post("/api/schedule-upload")
def api_schedule_upload(req: DbUploadRequest):
    job_id = str(uuid.uuid4())
    status = "scheduled" if req.scheduled_time else "running"
    
    db_manager.create_upload_job(
        job_id,
        req.video_generation_id,
        req.platforms,
        {
            "title": req.youtube_title,
            "description": req.youtube_description,
            "tags": req.youtube_tags,
            "privacy": req.youtube_privacy
        },
        {
            "caption": req.instagram_caption
        },
        status=status,
        scheduled_time=req.scheduled_time
    )
    
    if status == "running":
        t = threading.Thread(target=process_upload_job, args=(job_id,))
        t.daemon = True
        t.start()
        
    return {"success": True, "job_id": job_id}

@app.get("/api/generation-status/{generation_id}")
def api_generation_status(generation_id: str):
    gen = db_manager.get_video_generation(generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
        
    rel_path = ""
    if gen.get("final_video_path"):
        rel_path = os.path.relpath(gen["final_video_path"], os.path.abspath(os.path.curdir))
        
    return {
        "status": gen["status"],
        "video_url": f"http://localhost:8000/{rel_path.replace(os.path.sep, '/')}" if rel_path else "",
        "storyboard": gen["storyboard"],
        "youtube_metadata": gen.get("script_data", {}).get("youtube_metadata") if gen.get("script_data") else None,
        "instagram_metadata": gen.get("script_data", {}).get("instagram_metadata") if gen.get("script_data") else None,
    }

# Backward compatibility endpoints for legacy app.js uploads
class UploadRequest(BaseModel):
    video_path: str
    platforms: List[str]
    youtube_title: Optional[str] = ""
    youtube_description: Optional[str] = ""
    youtube_tags: Optional[List[str]] = []
    youtube_privacy: Optional[str] = "private"
    instagram_caption: Optional[str] = ""

@app.post("/api/upload")
def api_upload(req: UploadRequest):
    # Find matching generation by final_video_path relative or absolute
    # If not found, create a placeholder generation
    generations = db_manager.list_video_generations()
    matching_gen_id = None
    for g in generations:
        if g.get("final_video_path") and (req.video_path in g["final_video_path"] or g["final_video_path"] in req.video_path):
            matching_gen_id = g["id"]
            break
            
    if not matching_gen_id:
        matching_gen_id = str(uuid.uuid4())
        db_manager.create_video_generation(matching_gen_id, "Legacy upload", "Legacy upload", None, None, status="completed")
        db_manager.update_video_generation(matching_gen_id, final_video_path=req.video_path)
        
    job_id = str(uuid.uuid4())
    db_manager.create_upload_job(
        job_id,
        matching_gen_id,
        req.platforms,
        {
            "title": req.youtube_title,
            "description": req.youtube_description,
            "tags": req.youtube_tags,
            "privacy": req.youtube_privacy
        },
        {
            "caption": req.instagram_caption
        },
        status="running"
    )
    
    t = threading.Thread(target=process_upload_job, args=(job_id,))
    t.daemon = True
    t.start()
    return {"job_id": job_id}

@app.get("/api/upload-status/{job_id}")
def get_upload_status(job_id: str):
    job = db_manager.get_upload_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    return job


@app.get("/api/trends")
def get_trends(geo: str = "IN"):
    import xml.etree.ElementTree as ET
    url = f"https://trends.google.com/trending/rss?geo={geo.upper()}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Failed to fetch Google Trends: HTTP {response.status_code}")
        
        root = ET.fromstring(response.text)
        namespaces = {
            'ht': 'https://trends.google.com/trending/rss'
        }
        
        items = []
        for item in root.findall('.//item'):
            title = item.find('title').text
            
            traffic_el = item.find('ht:approx_traffic', namespaces)
            traffic = traffic_el.text if traffic_el is not None else "Unknown"
            
            picture_el = item.find('ht:picture', namespaces)
            picture_url = picture_el.text if picture_el is not None else ""
            
            news_items = []
            for news in item.findall('ht:news_item', namespaces):
                news_title = news.find('ht:news_item_title', namespaces)
                news_snippet = news.find('ht:news_item_snippet', namespaces)
                news_url = news.find('ht:news_item_url', namespaces)
                
                news_items.append({
                    "title": news_title.text if news_title is not None else "",
                    "snippet": news_snippet.text if news_snippet is not None else "",
                    "url": news_url.text if news_url is not None else ""
                })
            
            top_news_title = news_items[0]["title"] if news_items else ""
            top_news_url = news_items[0]["url"] if news_items else ""
            top_news_snippet = news_items[0]["snippet"] if news_items else ""
            
            items.append({
                "title": title,
                "traffic": traffic,
                "picture_url": picture_url,
                "news_title": top_news_title,
                "news_url": top_news_url,
                "news_snippet": top_news_snippet,
                "all_news": news_items
            })
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing Google Trends feed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
