import os
import sys
import time
import json
import requests
import configparser
import subprocess
import soundfile as sf
import gradio as gr
from dotenv import load_dotenv

# Load search helper
from search_helper import get_web_grounding_context, clean_json_response


# API configuration
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Voice map for Kokoro ONNX
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

# Leonardo Models
LEONARDO_MODELS = {
    "Leonardo Phoenix 1.0 (General/Realistic)": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",
    "Lucid Origin (Realistic Portrait)": "7b592283-e8a7-4c5a-9ba6-d18c31f258b9",
    "Lucid Realism (High Quality Face)": "05ce0082-2d80-4a2d-8653-4d1c85e2418e",
    "Flux Dev (SOTA Quality)": "b2614463-296c-462a-9586-aafdb8f00e36",
    "Leonardo Kino XL (Cinematic)": "aa77f04e-3eec-4034-9c07-d0f619684628",
    "Leonardo Vision XL (Artistic XL)": "5c232a9e-9061-4777-980a-ddc8e65647c6"
}

# Dimensions map for Aspect Ratios
ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "16:9": (1024, 576),
    "9:16": (576, 1024),
    "4:3": (1024, 768),
    "3:2": (1024, 680)
}

def get_video_dimensions(path):
    """Inspect video dimensions (width, height) using ffprobe."""
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
    return 576, 1024  # Default fallback to 9:16 aspect ratio

def has_audio_stream(path):
    """Check if the video has an audio stream using ffprobe."""
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

def download_b_roll(url):
    """Download video from URL to a local temp file, mimicking browser headers."""
    if not url or not url.strip().startswith(("http://", "https://")):
        return None
    url = url.strip()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        os.makedirs("temp", exist_ok=True)
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        if response.status_code == 200:
            out_path = os.path.abspath(os.path.join("temp", f"broll_{int(time.time())}.mp4"))
            with open(out_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
    except Exception as e:
        print(f"Error downloading background B-roll: {e}")
    return None

def composite_videos(b_roll_path, presenter_path, layout, output_path):
    """Composite B-roll and presenter video together using FFmpeg filters.
    - Split-Screen: stacks cropped top (B-roll) and bottom (presenter).
    - Picture-in-Picture: overlays small presenter in bottom right of B-roll.
    - Chroma Key: keys green background out of presenter, overlays on B-roll.
    """
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
        # No composite
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", presenter_path,
            "-c:v", "copy",
            "-c:a", "copy",
            output_path
        ]
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        return (res.returncode == 0), f"Copy presenter only: {res.stderr or res.stdout}"

    audio_map = ["-map", "1:a"] if has_audio_stream(presenter_path) else []
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", b_roll_path,
        "-i", presenter_path,
        "-filter_complex", filter_complex,
        "-map", "[v]"
    ] + audio_map + [
        "-shortest",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        output_path
    ]

    try:
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_path):
            return True, "Compositing succeeded!"
        else:
            return False, f"FFmpeg compositing failed: {res.stderr or res.stdout}"
    except Exception as e:
        return False, f"Exception during compositing: {e}"

MUSIC_PRESETS = {
    "Cinematic": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "Upbeat": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "Mysterious": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "Ambient": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3"
}

def download_music_preset(preset_name):
    """Download background music preset if not present locally."""
    if preset_name not in MUSIC_PRESETS:
        return None
    
    os.makedirs(os.path.join("assets", "music"), exist_ok=True)
    target_path = os.path.abspath(os.path.join("assets", "music", f"{preset_name.lower()}.mp3"))
    
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return target_path
        
    url = MUSIC_PRESETS[preset_name]
    try:
        print(f"Downloading background music preset '{preset_name}' from {url}...")
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            with open(target_path, "wb") as f:
                f.write(resp.content)
            return target_path
    except Exception as e:
        print(f"Error downloading music preset {preset_name}: {e}")
    return None

def generate_multi_scene_script(prompt, model, enable_search: bool = False):
    """Generate a structured 5-scene JSON script using Ollama."""
    url = f"{OLLAMA_HOST}/api/generate"
    
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

    system_prompt = (
        "You are an expert viral TikTok, YouTube Shorts, and Instagram Reels writer. "
        "Your task is to generate a highly engaging 15-second script about the requested topic, "
        "broken down into exactly 5 sequential scenes. "
        "To ensure visual continuity and keep the focus point consistent (so the video does not look like a series of unrelated random images), you MUST define:\n"
        "1. A 'global_visual_style' representing the overall visual medium, art style, camera/lighting style, and color palette (e.g. 'cinematic 3D render, dark mood, neon green accents, highly detailed, 8k').\n"
        "2. A 'global_subject_focus' describing the main character, subject, or object that remains constant across the entire story (e.g. 'a futuristic female astronaut wearing a white helmet with a gold visor').\n"
        "If verified facts are provided under VERIFIED INTERNET SEARCH FACTS, you MUST strictly ground your narration in those facts to ensure correctness.\n"
        "Respond ONLY with a valid JSON object matching this exact format, with no markdown styling, no conversational filler, and no extra text:\n"
        "{\n"
        "  \"topic\": \"Engaging vertical title of the video\",\n"
        "  \"background_music_style\": \"Cinematic\",\n"
        "  \"global_visual_style\": \"Overall art style, camera/lighting, and palette description\",\n"
        "  \"global_subject_focus\": \"Description of the main character/object focus point\",\n"
        "  \"scenes\": [\n"
        "    {\n"
        "      \"narration\": \"A short engaging narrator sentence (approx. 7-8 words).\",\n"
        "      \"visual_prompt\": \"Specific action, pose, or background setting representing the scene's narration, designed to be combined with the global style and subject description. Do not include camera frames or devices in the prompt.\"\n"
        "    },\n"
        "    ... (exactly 5 scenes)\n"
        "  ],\n"
        "  \"youtube_metadata\": {\n"
        "    \"title\": \"Catchy optimized YouTube Shorts title (max 100 chars)\",\n"
        "    \"description\": \"SEO-friendly description with relevant search keywords and tags\",\n"
        "    \"tags\": [\"shorts\", \"facts\", \"viral\", \"topic\"]\n"
        "  },\n"
        "  \"instagram_metadata\": {\n"
        "    \"caption\": \"Engaging Instagram Reels caption with emojis and relevant hashtags\"\n"
        "  }\n"
        "}"
    )
    
    full_prompt = f"System: {system_prompt}\n{grounding_info}\nUser: Write a viral 15-second script for: {prompt}"
    
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
            cleaned = clean_json_response(resp_text)
            data = json.loads(cleaned)
            if "scenes" in data and len(data["scenes"]) == 5:
                return data
            else:
                raise ValueError("JSON generated, but does not contain exactly 5 scenes.")
    except Exception as e:
        print(f"JSON script generation failed or returned invalid structure: {e}. Falling back to default script.")
        
    return {
        "topic": prompt if prompt else "Incredible Facts",
        "background_music_style": "Cinematic",
        "global_visual_style": "realistic vertical 9:16 portrait, cinematic lighting, dramatic mood, high-detail",
        "global_subject_focus": "a detailed mysterious mechanical box emitting faint golden light",
        "scenes": [
            {
                "narration": f"Here is an incredible fact about {prompt or 'our world'}.",
                "visual_prompt": "resting on a dust-covered desk inside a dark ancient study room"
            },
            {
                "narration": "Scientists were completely shocked when they discovered this secret.",
                "visual_prompt": "slowly unlocking itself as gears slide outward"
            },
            {
                "narration": "It changes everything we thought we knew about history.",
                "visual_prompt": "opening wide, revealing a small floating miniature galaxy inside"
            },
            {
                "narration": "The implications could reshape our entire future.",
                "visual_prompt": "projecting bright blue holographic stars onto the study walls"
            },
            {
                "narration": "Follow for more mind-blowing facts every single day!",
                "visual_prompt": "closing shut, leaving glowing golden sparks in the air"
            }
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

def generate_scene_image(prompt, model_key, aspect_ratio, progress=gr.Progress()):
    """Generate a scene image using Leonardo.ai and return (path, image_id)."""
    if not LEONARDO_API_KEY:
        return None, None
        
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
                            os.makedirs("temp", exist_ok=True)
                            out_path = os.path.abspath(os.path.join("temp", f"scene_{int(time.time())}_{image_id[:8]}.png"))
                            with open(out_path, "wb") as f:
                                f.write(img_data)
                            return out_path, image_id
                    elif gen_data.get("status") == "FAILED":
                        break
    except Exception as e:
        print(f"Error generating scene image: {e}")
    return None, None

def generate_leonardo_motion_api(image_id, prompt, progress=gr.Progress()):
    """Submit an Image-to-Video motion generation request to Leonardo.ai and poll until complete."""
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
                    status = gen_data.get("status")
                    if status == "COMPLETE":
                        videos = gen_data.get("generated_images", [])
                        if videos:
                            video_url = videos[0].get("url")
                            vid_data = requests.get(video_url).content
                            os.makedirs("temp", exist_ok=True)
                            out_path = os.path.abspath(os.path.join("temp", f"motion_{int(time.time())}.mp4"))
                            with open(out_path, "wb") as f:
                                f.write(vid_data)
                            return out_path
                    elif status == "FAILED":
                        break
    except Exception as e:
        print(f"Error generating Leonardo motion video: {e}")
    return None

def run_viral_shorts_pipeline(prompt, model, visual_mode, music_style, custom_music_file, voice_key, speed, leonardo_model, enable_search: bool = False, progress=gr.Progress()):
    """Execute the full 15-second multi-scene automated viral shorts generator pipeline.
    Returns: (output_video_path, storyboard_html_or_json, status_message)
    """
    progress(0.0, desc="Generating 5-scene script using Ollama...")
    script_data = generate_multi_scene_script(prompt, model, enable_search=enable_search)
    topic = script_data.get("topic", "Viral Short")
    scenes = script_data.get("scenes", [])
    
    os.makedirs("temp", exist_ok=True)
    
    bg_music_path = None
    if custom_music_file:
        bg_music_path = custom_music_file
    elif music_style != "None":
        progress(0.1, desc="Downloading/resolving background music track...")
        bg_music_path = download_music_preset(music_style)
        
    scene_videos = []
    scene_audios = []
    storyboard = []
    
    for idx, scene in enumerate(scenes):
        sc_num = idx + 1
        progress(0.1 + (idx / 5.0) * 0.8, desc=f"Processing Scene {sc_num}/5: {scene['narration'][:30]}...")
        
        # Combine scene prompt with global visual style and subject if present
        global_style = script_data.get("global_visual_style", "") if script_data else ""
        global_subject = script_data.get("global_subject_focus", "") if script_data else ""
        combined_prompt_parts = []
        if global_subject:
            combined_prompt_parts.append(global_subject)
        combined_prompt_parts.append(scene["visual_prompt"])
        if global_style:
            combined_prompt_parts.append(global_style)
        final_visual_prompt = ", ".join(combined_prompt_parts)
        
        # 1. Synthesize Scene Voiceover
        sc_text = scene["narration"]
        sc_audio, tts_msg = generate_speech_api(sc_text, voice_key, speed, "Normal")
        if not sc_audio:
            return None, None, f"Failed voice synthesis at Scene {sc_num}: {tts_msg}"
            
        info = sf.info(sc_audio)
        sc_duration = info.duration
        scene_audios.append(sc_audio)
        
        # 2. Generate Scene Visual
        sc_img_path, image_id = generate_scene_image(final_visual_prompt, leonardo_model, "9:16", progress)
        if not sc_img_path:
            return None, None, f"Failed image generation at Scene {sc_num}"
            
        scene_video_path = os.path.abspath(os.path.join("temp", f"scene_vid_{int(time.time())}_{idx}.mp4"))
        
        # 3. Create Scene Video Segment
        current_visual_mode = visual_mode
        if current_visual_mode == "Leonardo Motion Video" and image_id:
            progress(0.1 + (idx / 5.0) * 0.8 + 0.08, desc=f"Scene {sc_num}/5: Generating motion video via Leonardo Motion...")
            motion_vid = generate_leonardo_motion_api(image_id, final_visual_prompt, progress)
            if motion_vid:
                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1",
                    "-i", motion_vid,
                    "-t", str(sc_duration),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    scene_video_path
                ]
                subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                print(f"Motion generation failed for Scene {sc_num}, falling back to static pan/zoom slideshow.")
                current_visual_mode = "Cinematic Slideshow"
                
        if current_visual_mode == "Cinematic Slideshow" or not image_id:
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", sc_img_path,
                "-t", str(sc_duration),
                "-r", "25",
                "-vf", f"scale=1920:3412,zoompan=z='min(zoom+0.001,1.3)':d={int(sc_duration*25)}:x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':s=1080x1920",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                scene_video_path
            ]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        scene_videos.append(scene_video_path)
        storyboard.append({
            "scene": sc_num,
            "narration": sc_text,
            "image": sc_img_path,
            "audio": sc_audio,
            "duration": sc_duration
        })
        
    # 4. Concatenate Scenes and Audios
    progress(0.9, desc="Merging scenes & narration...")
    merged_video = os.path.abspath(os.path.join("temp", f"merged_video_{int(time.time())}.mp4"))
    merged_audio = os.path.abspath(os.path.join("temp", f"merged_audio_{int(time.time())}.wav"))
    
    video_list_path = os.path.abspath(os.path.join("temp", f"video_list_{int(time.time())}.txt"))
    audio_list_path = os.path.abspath(os.path.join("temp", f"audio_list_{int(time.time())}.txt"))
    
    with open(video_list_path, "w") as vf:
        for p in scene_videos:
            vf.write(f"file '{p}'\n")
            
    with open(audio_list_path, "w") as af:
        for p in scene_audios:
            af.write(f"file '{p}'\n")
            
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", video_list_path,
        "-c", "copy",
        merged_video
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", audio_list_path,
        "-c", "copy",
        merged_audio
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 5. Mix Audio and Background Music
    progress(0.95, desc="Mixing background music & final output render...")
    final_output_path = os.path.abspath(os.path.join("temp", f"viral_reel_{int(time.time())}.mp4"))
    
    if bg_music_path and os.path.exists(bg_music_path):
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", merged_video,
            "-i", merged_audio,
            "-stream_loop", "-1",
            "-i", bg_music_path,
            "-filter_complex", "[2:a]volume=0.15[bgm]; [1:a][bgm]amix=inputs=2:duration=first[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            final_output_path
        ]
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", merged_video,
            "-i", merged_audio,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            final_output_path
        ]
        
    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        os.remove(video_list_path)
        os.remove(audio_list_path)
    except Exception:
        pass
        
    # Format storyboard into a clean display layout (JSON-string for Gradio)
    storyboard_display = json.dumps(storyboard, indent=2)
        
    return final_output_path, storyboard_display, f"Successfully generated YouTube Reel for topic: {topic}!"


def fetch_trends_gradio(geo):
    import requests
    try:
        r = requests.get(f"http://localhost:8000/api/trends?geo={geo}", timeout=10)
        if r.status_code == 200:
            trends = r.json()
            choices = []
            html_content = "<div style='display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin-top: 15px;'>"
            for t in trends:
                title = t.get("title", "")
                traffic = t.get("traffic", "Unknown")
                news_title = t.get("news_title", "")
                news_url = t.get("news_url", "#")
                pic = t.get("picture_url", "")
                
                choices.append(title)
                
                img_tag = f"<img src='{pic}' style='width: 100%; height: 120px; object-fit: cover; border-radius: 8px;'/>" if pic else "<div style='height: 120px; background: #1e293b; display: flex; align-items: center; justify-content: center; border-radius: 8px; color: #475569;'>No Image</div>"
                
                news_tag = f"<p style='font-size: 0.85em; margin: 5px 0 0 0;'><b>News</b>: <a href='{news_url}' target='_blank' style='color: #c084fc; text-decoration: none;'>{news_title}</a></p>" if news_title else ""
                
                html_content += f"""
                <div style='background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #334155;'>
                    {img_tag}
                    <h4 style='margin: 8px 0 2px 0; color: #f1f5f9; font-size: 1.05em;'>{title}</h4>
                    <span style='background: #ef4444; color: #fff; font-size: 0.75em; padding: 2px 6px; border-radius: 12px; font-weight: bold;'>🔥 {traffic}</span>
                    {news_tag}
                </div>
                """
            html_content += "</div>"
            return gr.update(choices=choices, value=choices[0] if choices else None), html_content
    except Exception as e:
        return gr.update(choices=[]), f"<p style='color: #ef4444;'>Failed to fetch trends: {str(e)}</p>"
    return gr.update(choices=[]), "<p style='color: #ef4444;'>Failed to fetch trends.</p>"


def select_trend_gradio(trend_title):
    if not trend_title:
        return gr.update(), gr.update()
    return trend_title, True


def run_viral_shorts_pipeline_adapter(prompt, model, visual_mode_ui, music_style, custom_music, voice, speed, leonardo_model, enable_search):
    mode = "Cinematic Slideshow" if "Slideshow" in visual_mode_ui else "Leonardo Motion Video"
    return run_viral_shorts_pipeline(prompt, model, mode, music_style, custom_music, voice, speed, leonardo_model, enable_search=enable_search)

def get_ollama_models():
    """Dynamically fetch available models from local Ollama service."""
    ollama_models = []
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if response.status_code == 200:
            ollama_models = [m['name'] for m in response.json().get("models", [])]
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

def generate_script_api(prompt, model):
    """Call Ollama to generate a presentation script."""
    if not prompt:
        return "Please enter a prompt."
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload, timeout=45)
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            return f"Error: Ollama returned status {response.status_code}: {response.text}"
    except Exception as e:
        return f"Error connecting to Ollama: {e}"

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

def generate_speech_api(text, voice_key, speed=1.0, effect="Normal"):
    """Synthesize voice using Kokoro-ONNX with optional pitch effect."""
    if not text:
        return None, "Please enter some text to synthesize."
    
    onnx_path = os.path.abspath(os.path.join("models", "kokoro-v1.0.onnx"))
    voices_path = os.path.abspath(os.path.join("models", "voices-v1.0.bin"))
    
    if not os.path.exists(onnx_path) or not os.path.exists(voices_path):
        return None, "Error: Kokoro model files not found in models/ directory. Make sure to run test_tts.py first."
        
    voice = KOKORO_VOICES.get(voice_key, "af_sarah")
    
    try:
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(onnx_path, voices_path)
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        
        os.makedirs("temp", exist_ok=True)
        raw_output_path = os.path.abspath(os.path.join("temp", f"voice_raw_{int(time.time())}.wav"))
        sf.write(raw_output_path, samples, sample_rate)
        
        audio_path = raw_output_path
        # Apply pitch shift using FFmpeg if requested
        if effect == "Kid (High Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_kid_{int(time.time())}.wav"))
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", raw_output_path,
                "-af", "asetrate=24000*1.3,atempo=1/1.3",
                pitch_output_path
            ]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                os.remove(raw_output_path)
            except Exception:
                pass
            audio_path = pitch_output_path
            
        elif effect == "Deep (Low Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_deep_{int(time.time())}.wav"))
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", raw_output_path,
                "-af", "asetrate=24000*0.82,atempo=1/0.82",
                pitch_output_path
            ]
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                os.remove(raw_output_path)
            except Exception:
                pass
            audio_path = pitch_output_path
            
        trimmed_path = trim_audio_silence(audio_path)
        return trimmed_path, "Speech synthesized successfully!"
    except Exception as e:
        return None, f"Error synthesizing speech: {e}"

def generate_presenter_api(prompt, model_key, aspect_ratio, progress=gr.Progress()):
    """Call Leonardo.ai to generate presenter portrait and poll until completion."""
    if not LEONARDO_API_KEY:
        return None, "Error: LEONARDO_API_KEY not found in environment settings."
    if not prompt:
        return None, "Please enter a description of the presenter."
        
    model_id = LEONARDO_MODELS.get(model_key, "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3")
    width, height = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))
    
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
        progress(0.1, desc="Submitting request to Leonardo.ai...")
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code != 200:
            return None, f"Leonardo API error: {response.status_code} - {response.text}"
            
        data = response.json()
        job_data = data.get("sdGenerationJob")
        if not job_data:
            return None, f"Invalid API response structure: {data}"
            
        generation_id = job_data.get("generationId")
        
        # Polling loop
        poll_url = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"
        max_attempts = 30
        for attempt in range(max_attempts):
            progress(0.2 + (attempt / max_attempts) * 0.7, desc=f"Generating presenter image (attempt {attempt+1}/{max_attempts})...")
            time.sleep(2)
            poll_resp = requests.get(poll_url, headers=headers, timeout=10)
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                generation = poll_data.get("generations_by_pk", {})
                status = generation.get("status")
                
                if status == "COMPLETE":
                    images = generation.get("generated_images", [])
                    if images:
                        image_url = images[0].get("url")
                        # Download image
                        img_data = requests.get(image_url).content
                        os.makedirs("temp", exist_ok=True)
                        output_img_path = os.path.abspath(os.path.join("temp", f"presenter_{int(time.time())}.png"))
                        with open(output_img_path, "wb") as handler:
                            handler.write(img_data)
                        return output_img_path, "Presenter image generated successfully!"
                    else:
                        return None, "Error: Completed generation has no images."
                elif status == "FAILED":
                    return None, "Leonardo image generation task failed."
            else:
                return None, f"Error checking job status: {poll_resp.status_code}"
                
        return None, "Timeout waiting for Leonardo image generation."
    except Exception as e:
        return None, f"Error during Leonardo image generation: {e}"

def run_lipsync_api(image_path, audio_path, quality, wav2lip_version, nosmooth, padding_u, padding_d, padding_l, padding_r, b_roll_file=None, b_roll_url="", layout="None (Presenter Only)", progress=gr.Progress()):
    """Loop portrait image to match audio duration using FFmpeg, then trigger Wav2Lip lipsync."""
    if not image_path or not os.path.exists(image_path):
        return None, "Error: Presenter image file not found."
    if not audio_path or not os.path.exists(audio_path):
        return None, "Error: Voice audio file not found."
        
    try:
        # Resolve B-roll path
        b_roll_path = None
        if b_roll_file:
            b_roll_path = b_roll_file
        elif b_roll_url and b_roll_url.strip():
            progress(0.05, desc="Downloading background B-roll video...")
            b_roll_path = download_b_roll(b_roll_url)
            if not b_roll_path:
                print("Warning: Background B-roll download failed. Proceeding with presenter only.")
                
        progress(0.1, desc="Analyzing audio file duration...")
        info = sf.info(audio_path)
        duration = info.duration
        
        progress(0.2, desc="FFmpeg: Converting image to looped video...")
        os.makedirs("temp", exist_ok=True)
        temp_video = os.path.abspath(os.path.join("temp", f"looped_input_{int(time.time())}.mp4"))
        
        # Build looped video using FFmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-t", str(duration),
            "-r", "25",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            temp_video
        ]
        
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        progress(0.4, desc="Configuring Easy-Wav2Lip parameters...")
        # Write config.ini inside Easy-Wav2Lip folder
        config = configparser.ConfigParser()
        config['OPTIONS'] = {
            'video_file': temp_video,
            'vocal_file': audio_path,
            'quality': quality,
            'output_height': 'full resolution',
            'wav2lip_version': wav2lip_version,
            'use_previous_tracking_data': 'True',
            'nosmooth': str(nosmooth),
            'preview_window': 'Full'
        }
        config['PADDING'] = {
            'u': str(padding_u),
            'd': str(padding_d),
            'l': str(padding_l),
            'r': str(padding_r)
        }
        config['MASK'] = {
            'size': '2.5',
            'feathering': '2',
            'mouth_tracking': 'False',
            'debug_mask': 'False'
        }
        config['OTHER'] = {
            'batch_process': 'False',
            'output_suffix': '_Easy-Wav2Lip',
            'include_settings_in_suffix': 'False',
            'preview_settings': 'False',
            'frame_to_preview': '100'
        }
        
        config_path = os.path.abspath(os.path.join("Easy-Wav2Lip", "config.ini"))
        with open(config_path, 'w') as configfile:
            config.write(configfile)
            
        progress(0.5, desc="Running Wav2Lip Lipsync models...")
        final_video_path = os.path.abspath(os.path.join("temp", f"output_{int(time.time())}.mp4"))
        
        # Execute Wav2Lip run.py with current working directory set to Easy-Wav2Lip
        wav2lip_cmd = [
            sys.executable,
            "run.py",
            "-video_file", temp_video,
            "-vocal_file", audio_path,
            "-output_file", final_video_path
        ]
        
        result = subprocess.run(
            wav2lip_cmd,
            cwd="Easy-Wav2Lip",
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return None, f"Lipsync execution failed: {result.stderr or result.stdout}"
            
        if os.path.exists(final_video_path):
            if layout != "None (Presenter Only)" and b_roll_path:
                progress(0.85, desc="Compositing B-roll and presenter video...")
                composite_output_path = os.path.abspath(os.path.join("temp", f"composite_{int(time.time())}.mp4"))
                success, msg = composite_videos(b_roll_path, final_video_path, layout, composite_output_path)
                if success:
                    return composite_output_path, f"Lipsync and B-roll compositing ({layout}) completed successfully!"
                else:
                    return final_video_path, f"Lipsync completed, but compositing failed: {msg}"
            return final_video_path, "Lipsync completed successfully!"
        else:
            return None, f"Lipsync complete, but final video was not written to: {final_video_path}"
            
    except Exception as e:
        return None, f"Error during lipsync phase: {e}"

def run_full_pipeline(script_prompt, ollama_model, visual_prompt, leonardo_model, aspect_ratio, voice_key, speed, voice_effect, quality, wav2lip_version, nosmooth, padding_u, padding_d, padding_l, padding_r, b_roll_file=None, b_roll_url="", layout="None (Presenter Only)", progress=gr.Progress()):
    """Executes the full pipeline step-by-step."""
    # Append green screen description automatically if chroma key is selected
    if layout == "Green Screen (Chroma Key Presenter on B-Roll)" and "green screen" not in visual_prompt.lower():
        visual_prompt = visual_prompt.strip()
        if not visual_prompt.endswith("."):
            visual_prompt += ","
        visual_prompt += " solid green screen background"

    # Step 1: Script
    progress(0.0, desc="1/4: Generating script using local Ollama model...")
    script = generate_script_api(script_prompt, ollama_model)
    if script.startswith("Error"):
        return None, None, None, script
        
    # Step 2: Voice
    progress(0.25, desc="2/4: Synthesizing voice audio via local Kokoro-ONNX...")
    audio_path, tts_msg = generate_speech_api(script, voice_key, speed, voice_effect)
    if not audio_path:
        return None, None, None, tts_msg
        
    # Step 3: Presenter Image
    progress(0.5, desc="3/4: Generating presenter image via Leonardo.ai REST API...")
    image_path, img_msg = generate_presenter_api(visual_prompt, leonardo_model, aspect_ratio, progress)
    if not image_path:
        return None, None, audio_path, img_msg
        
    # Step 4: Lipsync & Compositing
    progress(0.75, desc="4/4: Triggering Wav2Lip model & compositing...")
    video_path, sync_msg = run_lipsync_api(
        image_path, audio_path, quality, wav2lip_version, nosmooth, 
        padding_u, padding_d, padding_l, padding_r, 
        b_roll_file, b_roll_url, layout, progress
    )
    if not video_path:
        return None, image_path, audio_path, sync_msg
        
    return video_path, image_path, audio_path, "Pipeline executed successfully! Final video generated below."

# CSS style sheet for custom dark/glassmorphism design
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');

body, html, .gradio-container {
    background: linear-gradient(135deg, #0c0a1c 0%, #150f29 50%, #0c0a1c 100%) !important;
    font-family: 'Outfit', sans-serif !important;
    color: #e2e8f0 !important;
}

/* Panel cards */
.block, .panel, .gr-box, .gr-padded, .gr-form {
    background: rgba(255, 255, 255, 0.03) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 18px !important;
    box-shadow: 0 10px 40px 0 rgba(0, 0, 0, 0.45) !important;
    padding: 20px !important;
    margin-bottom: 15px !important;
}

/* Input Fields and Dropdowns */
input, textarea, select, .gr-text-input {
    background-color: rgba(20, 15, 38, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    color: #f8fafc !important;
    border-radius: 10px !important;
}
input:focus, textarea:focus, select:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.25) !important;
}

/* Custom Buttons styling */
.primary-btn {
    background: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%) !important;
    border: none !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 16px !important;
    padding: 12px 24px !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 20px rgba(168, 85, 247, 0.45) !important;
    cursor: pointer !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
.primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 30px rgba(168, 85, 247, 0.65) !important;
}

.secondary-btn {
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    color: #f8fafc !important;
    font-weight: 500 !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
.secondary-btn:hover {
    background: rgba(255, 255, 255, 0.1) !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
}

/* Accordion and tabs */
.tabitem {
    border: none !important;
    padding: 10px 0px !important;
}
button.selected {
    background: rgba(168, 85, 247, 0.15) !important;
    color: #d8b4fe !important;
    border-bottom: 2px solid #a855f7 !important;
}

/* Header design */
.app-header {
    text-align: center;
    margin-bottom: 30px;
}
.app-title {
    font-size: 38px !important;
    background: linear-gradient(90deg, #818cf8, #c084fc, #fb7185);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
    margin-bottom: 5px !important;
}
.app-subtitle {
    font-size: 16px !important;
    color: #94a3b8 !important;
}
"""

# Load initial Ollama models list
ollama_models_list = get_ollama_models()

with gr.Blocks(title="AI Video Presenter Generator") as demo:
    gr.HTML(
        """
        <div class="app-header">
            <h1 class="app-title">🎬 AI Video Presenter Generator</h1>
            <p class="app-subtitle">Create realistic talking head videos from text using local Ollama, Kokoro ONNX, Leonardo.ai & Wav2Lip</p>
        </div>
        """
    )
    
    with gr.Tabs():
        # TAB 1: Unified Pipeline
        with gr.TabItem("🚀 Full Generation Pipeline"):
            with gr.Row():
                with gr.Column(scale=5):
                    gr.HTML("<h3 style='color: #c084fc;'>1. Script settings (Ollama)</h3>")
                    script_prompt = gr.Textbox(
                        label="Script Prompt",
                        placeholder="Write a prompt for Ollama to generate a presentation script...",
                        lines=3,
                        value="Write a highly engaging 15-second script (about 35-40 words) for a YouTube Short about a fascinating science fact."
                    )
                    ollama_model = gr.Dropdown(
                        label="Ollama Model",
                        choices=ollama_models_list,
                        value=ollama_models_list[0] if ollama_models_list else "minimax-m3:cloud"
                    )
                    
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>2. Voice settings (Kokoro)</h3>")
                    with gr.Row():
                        voice_select = gr.Dropdown(
                            label="Presenter Voice",
                            choices=list(KOKORO_VOICES.keys()),
                            value="Sarah (Female - US - Soft)"
                        )
                        voice_speed = gr.Slider(
                            label="Speech Speed",
                            minimum=0.5,
                            maximum=2.0,
                            value=1.0,
                            step=0.1
                        )
                        voice_effect = gr.Dropdown(
                            label="Voice Pitch Effect",
                            choices=["Normal", "Kid (High Pitch)", "Deep (Low Pitch)"],
                            value="Normal"
                        )
                        
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>3. Presenter Portrait (Leonardo.ai)</h3>")
                    presenter_prompt = gr.Textbox(
                        label="Visual Portrait Prompt",
                        placeholder="Describe what the presenter should look like...",
                        lines=2,
                        value="High quality vertical 9:16 portrait of a friendly talking presenter facing the camera, modern studio background, suitable for a YouTube Short, highly detailed face"
                    )
                    with gr.Row():
                        leonardo_model = gr.Dropdown(
                            label="Leonardo Model",
                            choices=list(LEONARDO_MODELS.keys()),
                            value="Lucid Realism (High Quality Face)"
                        )
                        aspect_ratio = gr.Dropdown(
                            label="Aspect Ratio",
                            choices=list(ASPECT_RATIO_DIMENSIONS.keys()),
                            value="9:16"
                        )
                        
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>4. Lipsync Quality Settings (Wav2Lip)</h3>")
                    with gr.Row():
                        wav2lip_quality = gr.Dropdown(
                            label="Lipsync Quality",
                            choices=["Fast", "Improved", "Enhanced"],
                            value="Enhanced"
                        )
                        wav2lip_v = gr.Dropdown(
                            label="Wav2Lip Model",
                            choices=["Wav2Lip", "Wav2Lip_GAN"],
                            value="Wav2Lip_GAN"
                        )
                        nosmooth_check = gr.Checkbox(
                            label="Disable smoothing (nosmooth)",
                            value=True
                        )
                    with gr.Accordion("Advanced Padding Adjustments", open=False):
                        with gr.Row():
                            pad_u = gr.Slider(label="Pad Top (U)", minimum=-50, maximum=50, value=0, step=1)
                            pad_d = gr.Slider(label="Pad Bottom (D)", minimum=-50, maximum=50, value=10, step=1)
                            pad_l = gr.Slider(label="Pad Left (L)", minimum=-50, maximum=50, value=0, step=1)
                            pad_r = gr.Slider(label="Pad Right (R)", minimum=-50, maximum=50, value=0, step=1)
                            
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>🎬 Storytelling B-Roll & Compositing</h3>")
                    with gr.Group():
                        with gr.Row():
                            b_roll_layout = gr.Dropdown(
                                label="Compositing Layout",
                                choices=[
                                    "None (Presenter Only)",
                                    "Split-Screen (Top B-Roll, Bottom Presenter)",
                                    "Picture-in-Picture (Presenter Bottom Right)",
                                    "Green Screen (Chroma Key Presenter on B-Roll)"
                                ],
                                value="None (Presenter Only)"
                            )
                        with gr.Row():
                            b_roll_file = gr.Video(label="Upload B-Roll Video File", format="mp4", height=200)
                            b_roll_url = gr.Textbox(
                                label="Or B-Roll Video URL",
                                placeholder="Enter direct MP4 video URL (e.g. from Pixabay)...",
                                lines=2
                            )

                    generate_btn = gr.Button("🚀 Generate AI Video", elem_classes="primary-btn")
                    
                with gr.Column(scale=4):
                    gr.HTML("<h3 style='color: #c084fc;'>Pipeline Output</h3>")
                    status_box = gr.Textbox(label="Status Logs", placeholder="Processing status logs will appear here...", interactive=False)
                    final_video = gr.Video(label="Final Generated Video", format="mp4", interactive=False)
                    
                    with gr.Accordion("Intermediate Pipeline Assets", open=True):
                        intermediate_img = gr.Image(label="Generated Presenter Image", type="filepath", interactive=False)
                        intermediate_audio = gr.Audio(label="Generated Voice Audio", type="filepath", interactive=False)
                        
            # Link elements
            generate_btn.click(
                fn=run_full_pipeline,
                inputs=[
                    script_prompt, ollama_model,
                    presenter_prompt, leonardo_model, aspect_ratio,
                    voice_select, voice_speed, voice_effect,
                    wav2lip_quality, wav2lip_v, nosmooth_check,
                    pad_u, pad_d, pad_l, pad_r,
                    b_roll_file, b_roll_url, b_roll_layout
                ],
                outputs=[final_video, intermediate_img, intermediate_audio, status_box]
            )

        # TAB 2: Manual Lipsync Tool
        with gr.TabItem("🎬 Manual Lipsync Tool"):
            gr.HTML("<p style='color: #94a3b8; margin-bottom: 20px;'>Upload your own portrait image (or video) and speech audio file to sync lips manually.</p>")
            with gr.Row():
                with gr.Column():
                    manual_image = gr.Image(label="Presenter Image / Video", type="filepath")
                    manual_audio = gr.Audio(label="Voice Audio File", type="filepath")
                    
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>Lipsync Settings</h3>")
                    with gr.Row():
                        m_quality = gr.Dropdown(
                            label="Lipsync Quality",
                            choices=["Fast", "Improved", "Enhanced"],
                            value="Enhanced"
                        )
                        m_wav2lip_v = gr.Dropdown(
                            label="Wav2Lip Model",
                            choices=["Wav2Lip", "Wav2Lip_GAN"],
                            value="Wav2Lip_GAN"
                        )
                        m_nosmooth_check = gr.Checkbox(
                            label="Disable smoothing (nosmooth)",
                            value=True
                        )
                    with gr.Accordion("Advanced Padding Adjustments", open=False):
                        with gr.Row():
                            m_pad_u = gr.Slider(label="Pad Top (U)", minimum=-50, maximum=50, value=0, step=1)
                            m_pad_d = gr.Slider(label="Pad Bottom (D)", minimum=-50, maximum=50, value=10, step=1)
                            m_pad_l = gr.Slider(label="Pad Left (L)", minimum=-50, maximum=50, value=0, step=1)
                            m_pad_r = gr.Slider(label="Pad Right (R)", minimum=-50, maximum=50, value=0, step=1)
                            
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>🎬 Storytelling B-Roll & Compositing</h3>")
                    with gr.Group():
                        with gr.Row():
                            m_b_roll_layout = gr.Dropdown(
                                label="Compositing Layout",
                                choices=[
                                    "None (Presenter Only)",
                                    "Split-Screen (Top B-Roll, Bottom Presenter)",
                                    "Picture-in-Picture (Presenter Bottom Right)",
                                    "Green Screen (Chroma Key Presenter on B-Roll)"
                                ],
                                value="None (Presenter Only)"
                            )
                        with gr.Row():
                            m_b_roll_file = gr.Video(label="Upload B-Roll Video File", format="mp4", height=200)
                            m_b_roll_url = gr.Textbox(
                                label="Or B-Roll Video URL",
                                placeholder="Enter direct MP4 video URL (e.g. from Pixabay)...",
                                lines=2
                            )

                    manual_btn = gr.Button("🎬 Sync Lips", elem_classes="primary-btn")
                    
                with gr.Column():
                    manual_video_out = gr.Video(label="Output Lipsynced Video", format="mp4", interactive=False)
                    manual_status = gr.Textbox(label="Status Logs", placeholder="Processing logs...", interactive=False)
                    
            manual_btn.click(
                fn=run_lipsync_api,
                inputs=[
                    manual_image, manual_audio,
                    m_quality, m_wav2lip_v, m_nosmooth_check,
                    m_pad_u, m_pad_d, m_pad_l, m_pad_r,
                    m_b_roll_file, m_b_roll_url, m_b_roll_layout
                ],
                outputs=[manual_video_out, manual_status]
            )

        # TAB 3: Script & TTS Studio
        with gr.TabItem("✍️ Script & TTS Studio"):
            with gr.Row():
                with gr.Column():
                    gr.HTML("<h3 style='color: #c084fc;'>1. Script Writer</h3>")
                    studio_script_prompt = gr.Textbox(
                        label="Script Prompt",
                        placeholder="Write a prompt for Ollama...",
                        lines=3
                    )
                    studio_ollama_model = gr.Dropdown(
                        label="Ollama Model",
                        choices=ollama_models_list,
                        value=ollama_models_list[0] if ollama_models_list else "minimax-m3:cloud"
                    )
                    script_gen_btn = gr.Button("✍️ Generate Script", elem_classes="secondary-btn")
                    
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 20px;'>2. Speech Studio</h3>")
                    with gr.Row():
                        studio_voice = gr.Dropdown(
                            label="Voice select",
                            choices=list(KOKORO_VOICES.keys()),
                            value="Sarah (Female - US - Soft)"
                        )
                        studio_speed = gr.Slider(
                            label="Speed",
                            minimum=0.5,
                            maximum=2.0,
                            value=1.0,
                            step=0.1
                        )
                        studio_effect = gr.Dropdown(
                            label="Voice Pitch Effect",
                            choices=["Normal", "Kid (High Pitch)", "Deep (Low Pitch)"],
                            value="Normal"
                        )
                    tts_gen_btn = gr.Button("🔊 Generate Audio", elem_classes="primary-btn")
                    
                with gr.Column():
                    script_output = gr.Textbox(label="Generated Script", lines=8)
                    audio_output = gr.Audio(label="Generated Speech Audio", type="filepath", interactive=False)
                    studio_status = gr.Textbox(label="Status Logs", interactive=False)
                    
            # Interactions
            script_gen_btn.click(
                fn=generate_script_api,
                inputs=[studio_script_prompt, studio_ollama_model],
                outputs=[script_output]
            )
            tts_gen_btn.click(
                fn=generate_speech_api,
                inputs=[script_output, studio_voice, studio_speed, studio_effect],
                outputs=[audio_output, studio_status]
            )

        # TAB 4: Presenter Studio (Leonardo.ai)
        with gr.TabItem("🎨 Presenter Portrait Studio"):
            with gr.Row():
                with gr.Column():
                    gr.HTML("<h3 style='color: #c084fc;'>Leonardo.ai Presenter Generator</h3>")
                    studio_presenter_prompt = gr.Textbox(
                        label="Visual Portrait Prompt",
                        placeholder="Describe what the presenter should look like...",
                        lines=4,
                        value="High resolution headshot portrait of a professional news anchor facing camera, neutral expression, soft studio lighting, high detailed face"
                    )
                    with gr.Row():
                        studio_leonardo_model = gr.Dropdown(
                            label="Leonardo Model",
                            choices=list(LEONARDO_MODELS.keys()),
                            value="Lucid Realism (High Quality Face)"
                        )
                        studio_aspect_ratio = gr.Dropdown(
                            label="Aspect Ratio",
                            choices=list(ASPECT_RATIO_DIMENSIONS.keys()),
                            value="9:16"
                        )
                    leonardo_btn = gr.Button("🎨 Generate Portrait Image", elem_classes="primary-btn")
                    
                with gr.Column():
                    image_output = gr.Image(label="Generated Portrait Image", type="filepath", interactive=False)
                    leonardo_status = gr.Textbox(label="Status Logs", interactive=False)
                    
            leonardo_btn.click(
                fn=generate_presenter_api,
                inputs=[studio_presenter_prompt, studio_leonardo_model, studio_aspect_ratio],
                outputs=[image_output, leonardo_status]
            )

        # TAB 5: Viral Shorts Studio (Daily Automated Reels Creator)
        with gr.TabItem("📱 Viral Shorts Studio"):
            gr.HTML(
                """
                <p style='color: #94a3b8; margin-bottom: 20px;'>
                    Generate a complete 15-second YouTube Short / Instagram Reel with a multi-scene voiceover narration, 
                    matching panning visuals, and mixed background music.
                </p>
                """
            )
            
            with gr.Accordion("🔥 Discover Trending Topics", open=False):
                with gr.Row():
                    geo_select = gr.Dropdown(
                        label="Country Region",
                        choices=["IN", "US", "GB", "CA", "AU"],
                        value="IN",
                        scale=2
                    )
                    fetch_trends_btn = gr.Button("Fetch Trending Topics", scale=1, variant="secondary")
                
                trends_choices = gr.Dropdown(
                    label="Available Trends (Select to use)",
                    choices=[],
                    interactive=True
                )
                
                trends_preview = gr.HTML(
                    "<p style='color: #64748b;'>Click 'Fetch Trending Topics' to see what's hot today.</p>"
                )
            
            with gr.Row():
                with gr.Column(scale=5):
                    gr.HTML("<h3 style='color: #c084fc;'>1. Short Video Topic</h3>")
                    viral_prompt = gr.Textbox(
                        label="Topic or Category Prompt",
                        placeholder="E.g. Fascinating quantum science fact, Derinkuyu underground city, bizarre space discoveries...",
                        value="The giant hidden ocean underneath Jupiter's moon Europa",
                        lines=2
                    )
                    viral_ollama_model = gr.Dropdown(
                        label="Ollama Model",
                        choices=ollama_models_list,
                        value=ollama_models_list[0] if ollama_models_list else "minimax-m3:cloud"
                    )
                    enable_search = gr.Checkbox(
                        label="Verify facts via Web Search (Fact-Checking RAG)",
                        value=False
                    )
                    
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>2. Visual Mode Settings</h3>")
                    with gr.Row():
                        visual_mode = gr.Dropdown(
                            label="Visual Format",
                            choices=["Cinematic Slideshow (Pan & Zoom)", "Leonardo Motion Video (Image-to-Video)"],
                            value="Cinematic Slideshow (Pan & Zoom)",
                            info="Slideshow applies Ken Burns effects to static images (fast & 0 credits). Leonardo Motion calls Video Gen API."
                        )
                        viral_leonardo_model = gr.Dropdown(
                            label="Leonardo Model",
                            choices=list(LEONARDO_MODELS.keys()),
                            value="Lucid Realism (High Quality Face)"
                        )
                        
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>3. Voice Narration</h3>")
                    with gr.Row():
                        viral_voice = gr.Dropdown(
                            label="Narrator Voice",
                            choices=list(KOKORO_VOICES.keys()),
                            value="Sarah (Female - US - Soft)"
                        )
                        viral_voice_speed = gr.Slider(
                            label="Speed",
                            minimum=0.5,
                            maximum=2.0,
                            value=1.0,
                            step=0.1
                        )
                        
                    gr.HTML("<h3 style='color: #c084fc; margin-top: 15px;'>4. Background Music</h3>")
                    with gr.Row():
                        music_style = gr.Dropdown(
                            label="Preset Style",
                            choices=["None", "Cinematic", "Upbeat", "Mysterious", "Ambient"],
                            value="Cinematic"
                        )
                        custom_music = gr.Audio(
                            label="Or Upload Custom Music Loop",
                            type="filepath"
                        )
                        
                    viral_generate_btn = gr.Button("📱 Generate Storytelling Short", elem_classes="primary-btn")
                    
                with gr.Column(scale=4):
                    gr.HTML("<h3 style='color: #c084fc;'>Short Output</h3>")
                    viral_status = gr.Textbox(
                        label="Pipeline Logs",
                        placeholder="Workflow status logs...",
                        interactive=False
                    )
                    viral_video_out = gr.Video(
                        label="Final Vertical Short Video",
                        format="mp4",
                        interactive=False
                    )
                    
                    with gr.Accordion("Generated Scene Storyboard", open=True):
                        storyboard_out = gr.Textbox(
                            label="Scene Script & Prompts (JSON)",
                            lines=10,
                            interactive=False
                        )
                        
            # Link click action
            viral_generate_btn.click(
                fn=run_viral_shorts_pipeline_adapter,
                inputs=[
                    viral_prompt, viral_ollama_model,
                    visual_mode, music_style, custom_music,
                    viral_voice, viral_voice_speed, viral_leonardo_model,
                    enable_search
                ],
                outputs=[viral_video_out, storyboard_out, viral_status]
            )
            
            fetch_trends_btn.click(
                fn=fetch_trends_gradio,
                inputs=[geo_select],
                outputs=[trends_choices, trends_preview]
            )
            
            trends_choices.change(
                fn=select_trend_gradio,
                inputs=[trends_choices],
                outputs=[viral_prompt, enable_search]
            )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, css=custom_css)
