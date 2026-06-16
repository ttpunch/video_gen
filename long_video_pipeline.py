import os
import sys
import time
import uuid
import json
import shutil
import subprocess
import requests
import soundfile as sf
from typing import Optional, List, Dict, Tuple

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

def search_pexels_video(query: str, api_key: str, orientation: str = "landscape") -> Optional[str]:
    """Search Pexels API for video clips matching the query and return the download URL."""
    if not api_key:
        print("[Pexels] API key is missing.")
        return None
    
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 5, "orientation": orientation}
    
    try:
        print(f"[Pexels] Searching for: '{query}' ({orientation})")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            videos = data.get("videos", [])
            if not videos:
                print(f"[Pexels] No videos found for query: '{query}'")
                return None
            
            # Select the first HD MP4 video file
            for video in videos:
                files = video.get("video_files", [])
                for f in files:
                    if f.get("file_type") == "video/mp4" and f.get("quality") == "hd":
                        return f.get("link")
                for f in files:
                    if f.get("file_type") == "video/mp4":
                        return f.get("link")
        else:
            print(f"[Pexels] API error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Pexels] Search error: {e}")
    return None

def download_video_file(url: str, output_path: str, max_retries: int = 3) -> bool:
    """Download a video file from a URL with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[Download] Fetching video (attempt {attempt}/{max_retries})...")
            response = requests.get(url, stream=True, timeout=45)
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    print(f"[Download] Successfully saved to: {output_path}")
                    return True
            else:
                print(f"[Download] Failed with status code: {response.status_code}")
        except Exception as e:
            print(f"[Download] Error on attempt {attempt}: {e}")
        time.sleep(3 * attempt)
    return False

def search_and_download_pexels(
    query: str, 
    api_key: str, 
    output_path: str, 
    global_focus: str = "", 
    orientation: str = "landscape"
) -> Optional[str]:
    """Robust wrapper that queries Pexels using broad fallbacks to ensure a video is downloaded."""
    # Clean query text
    clean_query = query.replace(",", "").replace(".", "").replace(";", "").strip()
    
    # Level 1: Full visual prompt keywords
    url = search_pexels_video(clean_query, api_key, orientation)
    if url and download_video_file(url, output_path):
        return output_path
        
    # Level 2: Simplified query (first 2-3 words)
    words = clean_query.split()
    if len(words) > 2:
        simplified = " ".join(words[:2])
        print(f"[Pexels Fallback] Trying simplified keywords: '{simplified}'")
        url = search_pexels_video(simplified, api_key, orientation)
        if url and download_video_file(url, output_path):
            return output_path
            
    # Level 3: Global focus point of the video
    if global_focus:
        print(f"[Pexels Fallback] Trying global subject focus: '{global_focus}'")
        url = search_pexels_video(global_focus, api_key, orientation)
        if url and download_video_file(url, output_path):
            return output_path
            
    # Level 4: Generic theme clip
    generic = "abstract space" if orientation == "landscape" else "abstract background"
    print(f"[Pexels Fallback] Trying generic theme: '{generic}'")
    url = search_pexels_video(generic, api_key, orientation)
    if url and download_video_file(url, output_path):
        return output_path
        
    return None

def generate_longform_script(prompt: str, model: str) -> Dict:
    """Generate a structured outline and scene-by-scene script for a 5-minute landscape video."""
    url = f"{OLLAMA_HOST}/api/generate"
    
    # Stage 1: Generate Outline
    outline_system = (
        "You are an expert documentary writer. Your task is to design a detailed outline for a 5-minute landscape documentary. "
        "Create exactly 20 sequential scene ideas. "
        "For each scene, describe a specific, generic real-world visual action or setting (e.g., 'flowing river water', 'city street at night') "
        "that can easily be searched as a stock video clip on Pexels.\n"
        "Respond ONLY with a valid JSON object matching this exact format, and no other text:\n"
        "{\n"
        "  \"topic\": \"Documentary Title\",\n"
        "  \"global_visual_style\": \"Cinematic landscape photography, realistic, 4k\",\n"
        "  \"global_subject_focus\": \"Main topic subject\",\n"
        "  \"scenes\": [\n"
        "    {\n"
        "      \"scene_num\": 1,\n"
        "      \"focus\": \"Short thematic description of this segment\",\n"
        "      \"visual_prompt\": \"Search query keywords (e.g. starry night sky, ocean waves)\"\n"
        "    },\n"
        "    ... (exactly 20 scenes)\n"
        "  ]\n"
        "}"
    )
    
    print("[Ollama] Drafting 20-scene documentary outline...")
    payload1 = {
        "model": model,
        "prompt": f"System: {outline_system}\nUser: Write an outline for: {prompt}.",
        "stream": False,
        "format": "json"
    }
    
    try:
        response1 = requests.post(url, json=payload1, timeout=60)
        if response1.status_code == 200:
            resp_text = response1.json().get("response", "").strip()
            from backend import clean_json_response
            cleaned = clean_json_response(resp_text)
            outline_data = json.loads(cleaned)
        else:
            raise Exception(f"Ollama outline request failed: {response1.status_code}")
    except Exception as e:
        print(f"[Ollama] Outline generation failed, using fallback: {e}")
        # Fallback 20-scene template
        outline_data = {
            "topic": prompt,
            "global_visual_style": "Cinematic landscape",
            "global_subject_focus": prompt,
            "scenes": [{"scene_num": i+1, "focus": f"Exploring {prompt}", "visual_prompt": "cinematic nature"} for i in range(20)]
        }
        
    scenes_outline = outline_data.get("scenes", [])
    global_style = outline_data.get("global_visual_style", "Cinematic")
    global_focus = outline_data.get("global_subject_focus", prompt)
    
    # Stage 2: Scene Narration Generation Loop
    print("[Ollama] Generating scene narratives scene-by-scene...")
    storyboard = []
    prev_narration = ""
    
    for idx, scene in enumerate(scenes_outline):
        scene_num = scene.get("scene_num", idx + 1)
        visual = scene.get("visual_prompt", "nature")
        focus = scene.get("focus", "")
        
        narration_prompt = (
            f"You are a professional documentary voiceover narrator.\n"
            f"Topic: {prompt}.\n"
            f"Scene {scene_num}/20. Segment Focus: {focus}.\n"
            f"Previous scene narration: '{prev_narration}'\n\n"
            f"Write exactly 1 sentence of narration for this scene. It must be highly engaging, educational, and flow naturally from the previous sentence. "
            f"Keep the word count strictly between 30 and 40 words. Do not include any formatting or scene headers—only write the raw narration sentence."
        )
        
        payload2 = {
            "model": model,
            "prompt": narration_prompt,
            "stream": False
        }
        
        scene_narration = ""
        try:
            response2 = requests.post(url, json=payload2, timeout=45)
            if response2.status_code == 200:
                scene_narration = response2.json().get("response", "").strip()
        except Exception as e:
            print(f"[Ollama] Narration failed for scene {scene_num}: {e}")
            
        if not scene_narration:
            scene_narration = f"We continue looking into the deep aspects of {prompt}, examining its features and visual dynamics."
            
        prev_narration = scene_narration
        
        storyboard.append({
            "scene": scene_num,
            "speaker": "Sarah", # Default voice narrator
            "narration": scene_narration,
            "visual_prompt": visual,
            "image_url": "",
            "image_path": "",
            "audio_url": "",
            "audio_path": "",
            "duration": 0.0
        })
        print(f"Scene {scene_num} narration: '{scene_narration[:40]}...'")
        
    return {
        "topic": outline_data.get("topic", prompt),
        "background_music_style": "Cinematic",
        "global_visual_style": global_style,
        "global_subject_focus": global_focus,
        "scenes": storyboard,
        "youtube_metadata": {
            "title": f"The Story of {outline_data.get('topic', prompt)} (Documentary)",
            "description": f"An in-depth 5-minute look into {prompt}. #documentary #video #knowledge",
            "tags": ["documentary", "science", "viral", "interesting"]
        },
        "instagram_metadata": {
            "caption": f"An in-depth exploration of {prompt}! 🧠🌍 #documentary #explore #viral"
        }
    }

def run_long_video_pipeline(
    generation_id: str,
    storyboard: List[Dict],
    pexels_api_key: str,
    voice: str = "Sarah (Female - US - Soft)",
    speed: float = 1.0,
    music_style: str = "Cinematic",
    enable_captions: bool = True,
    caption_font: str = "Arial",
    caption_size: int = 32,
    caption_margin_v: int = 80,
    caption_color: str = "&H00FFFF&",
    enable_transition_sfx: bool = True
) -> Tuple[str, List[Dict]]:
    """Download Pexels videos, generate TTS audio, crop, loop, mix audio, and burn landscape subtitles."""
    from backend import generate_speech_audio, generate_ass_subtitles, mix_transition_sfx, download_music_preset, map_speaker_to_voice_key
    
    timestamp = int(time.time())
    working_dir = os.path.abspath(os.path.join("temp", f"long_{generation_id}"))
    os.makedirs(working_dir, exist_ok=True)
    
    scene_videos = []
    scene_audios = []
    updated_storyboard = []
    
    print(f"[Pipeline] Starting rendering for generation {generation_id} ({len(storyboard)} scenes)...")
    
    for idx, scene in enumerate(storyboard):
        sc_num = scene["scene"]
        narration = scene["narration"]
        visual = scene["visual_prompt"]
        
        # 1. Synthesize audio
        audio_filename = f"scene_audio_{sc_num}_{timestamp}.wav"
        sc_audio_path = os.path.join(working_dir, audio_filename)
        
        voice_key = map_speaker_to_voice_key(scene.get("speaker", voice))
        speech_path, msg = generate_speech_audio(narration, voice_key, speed, "Normal")
        if not speech_path or not os.path.exists(speech_path):
            raise Exception(f"Failed to synthesize voice for scene {sc_num}: {msg}")
            
        shutil.copy(speech_path, sc_audio_path)
        info = sf.info(sc_audio_path)
        sc_duration = info.duration
        scene_audios.append(sc_audio_path)
        
        # 2. Search & Download Pexels Video
        video_filename = f"pexels_raw_{sc_num}_{timestamp}.mp4"
        raw_video_path = os.path.join(working_dir, video_filename)
        
        downloaded = search_and_download_pexels(
            visual, pexels_api_key, raw_video_path, global_focus=visual, orientation="landscape"
        )
        if not downloaded or not os.path.exists(raw_video_path):
            raise Exception(f"Could not retrieve Pexels video for scene {sc_num} prompt '{visual}'")
            
        # 3. Format Scene Video Segment with FFmpeg
        # Scales/crops video to exactly 1920x1080 (16:9 Landscape), loops it (-stream_loop -1), and merges audio
        scene_segment_path = os.path.abspath(os.path.join(working_dir, f"segment_{sc_num}.mp4"))
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts",
            "-stream_loop", "-1", "-an", "-i", raw_video_path,
            "-i", sc_audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", str(sc_duration),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
            "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            scene_segment_path
        ]
        
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        scene_videos.append(scene_segment_path)
        
        # Add to updated storyboard data
        img_rel = os.path.relpath(raw_video_path, os.path.abspath(os.path.curdir))
        aud_rel = os.path.relpath(sc_audio_path, os.path.abspath(os.path.curdir))
        
        updated_storyboard.append({
            "scene": sc_num,
            "speaker": scene.get("speaker", voice),
            "narration": narration,
            "visual_prompt": visual,
            "image_url": "", # Optional image preview
            "image_path": "",
            "image_id": "",
            "video_url": f"http://localhost:8000/{img_rel.replace(os.path.sep, '/')}",
            "video_path": raw_video_path,
            "audio_url": f"http://localhost:8000/{aud_rel.replace(os.path.sep, '/')}",
            "audio_path": sc_audio_path,
            "duration": sc_duration
        })
        print(f"[Pipeline] Scene {sc_num} compiled successfully. Duration: {sc_duration:.2f}s")

    # 4. Concatenate segments
    merged_video = os.path.abspath(os.path.join(working_dir, f"merged_video_{timestamp}.mp4"))
    merged_audio = os.path.abspath(os.path.join(working_dir, f"merged_audio_{timestamp}.wav"))
    
    video_list_path = os.path.abspath(os.path.join(working_dir, f"video_list_{timestamp}.txt"))
    audio_list_path = os.path.abspath(os.path.join(working_dir, f"audio_list_{timestamp}.txt"))
    
    with open(video_list_path, "w") as vf:
        for p in scene_videos:
            vf.write(f"file '{p}'\n")
    with open(audio_list_path, "w") as af:
        for p in scene_audios:
            af.write(f"file '{p}'\n")
            
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", video_list_path, "-c", "copy", merged_video], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_list_path, "-c", "copy", merged_audio], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 5. Mix Background Music
    bg_music_path = download_music_preset(music_style) if music_style != "None" else None
    audio_mixed = os.path.abspath(os.path.join(working_dir, f"audio_mixed_{timestamp}.wav"))
    
    if bg_music_path and os.path.exists(bg_music_path):
        # Loops bg music indefinitely, mixes it with the voice narration
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_audio, "-stream_loop", "-1", "-i", bg_music_path,
            "-filter_complex", "[1:a]volume=0.15[bgm]; [0:a][bgm]amix=inputs=2:duration=first[a]",
            "-map", "[a]", "-c:a", "pcm_s16le", audio_mixed
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.copy(merged_audio, audio_mixed)
        
    # Mix transition SFX into audio
    transition_times = []
    curr_t = 0.0
    for sc in updated_storyboard[:-1]:
        curr_t += sc["duration"]
        transition_times.append(curr_t)
        
    audio_final_mixed = os.path.abspath(os.path.join(working_dir, f"audio_final_mixed_{timestamp}.wav"))
    if enable_transition_sfx:
        mix_transition_sfx(audio_mixed, audio_final_mixed, transition_times)
    else:
        shutil.copy(audio_mixed, audio_final_mixed)
        
    # Combine final video & audio
    processed_video = os.path.abspath(os.path.join(working_dir, f"processed_video_{timestamp}.mp4"))
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", merged_video, "-i", audio_final_mixed,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", processed_video
    ]
    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 6. Burn Landscape Subtitles
    final_output = os.path.abspath(os.path.join("outputs", f"long_reel_{timestamp}.mp4"))
    os.makedirs("outputs", exist_ok=True)
    
    if enable_captions:
        ass_path = os.path.abspath(os.path.join(working_dir, f"subtitles_{timestamp}.ass"))
        # alignment 2 = centered bottom, which is standard for landscape format.
        generate_ass_subtitles(
            updated_storyboard, ass_path, caption_font, caption_size,
            margin_v=caption_margin_v, alignment=2, highlight_color=caption_color,
            style_mode="Standard"
        )
        
        sub_filter = f"subtitles='{os.path.relpath(ass_path, os.path.abspath(os.path.curdir))}'"
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", processed_video, "-vf", sub_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", final_output
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.copy(processed_video, final_output)
        
    # Cleanup temp workspace dir
    # try:
    #     shutil.rmtree(working_dir)
    # except Exception:
    #     pass
        
    return final_output, updated_storyboard
