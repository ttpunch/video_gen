import os
import sys
import time
import json
import uuid
import requests
import configparser
import hashlib
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
import cost_tracker
import image_providers
import video_quality as vq
from hailuo import generate_hailuo_video
from reliability import retry_call, RetryError
from notifier import notify
import script_utils
import stock_footage
from script_utils import build_storyboard_from_story, normalize_scene_count
from script_validator import validate_script, autofix, ART_STYLE_PRESETS
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

# Every autonomous video used to hardcode "Did You Know? (Fact Hook)" (see
# viral_agent.py's ``_run_single_video``), so every unattended upload opened
# with the identical hook regardless of topic -- a large, previously invisible
# contributor to "the videos feel similar". The scheduler now rotates through
# this whole set (see ROTATING_HOOK_STYLES below); the two entries marked NEW
# fill formulas that 2026 short-form research names as the highest and
# second-highest performing hook types, and were not covered by the original
# five (which cluster around one "did you know / secrets" register).
VIRAL_HOOKS = {
    "None (Direct Prompt)": "",
    "Did You Know? (Fact Hook)": "Start the script with a mind-blowing 'Did you know...' hook in Scene 1 to grab immediate attention.",
    "3 Shocking Secrets": "Frame the script around '3 shocking secrets they don't want you to know', starting with a high-intensity hook in Scene 1.",
    "I Was Today Years Old": "Start the script with 'I was today years old when I found out this mind-blowing truth...' in Scene 1.",
    "This Changes Everything": "Start with 'This insane discovery changes everything we thought we knew about history...' in Scene 1.",
    "Banned Facts": "Start with 'These are the banned facts they tried to hide from us...' in Scene 1.",
    "Contrarian Claim (NEW)": "Open by stating the thing most people believe about the topic, then flatly contradict it in the same breath (e.g. 'Everyone thinks X. They're wrong.'). No hedging.",
    "Mistake Warning (NEW)": "Open by naming a specific, common mistake almost everyone makes related to the topic, framed as a direct warning to the viewer (e.g. 'You've been doing X wrong your whole life.').",
}

#: Hook styles the autonomous scheduler rotates through, one per video, never
#: repeating the immediately previous pick. "None (Direct Prompt)" is excluded
#: here -- an unattended video with no hook instruction is exactly the
#: generic-feeling failure mode this rotation exists to prevent.
ROTATING_HOOK_STYLES = [k for k in VIRAL_HOOKS if k != "None (Direct Prompt)"]

# Helpers
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
    # normalize=0 is essential. amix's default normalization divides every input
    # by the input count, so adding N whooshes silently attenuated the entire
    # narration by a factor of N+1 -- measured at -13 dB with 4 transitions.
    #
    # dropout_transition=0 matters just as much: by default amix ramps the gain
    # back up over 2 seconds each time an input ENDS, and each whoosh ends at a
    # different moment. That produced a staircase of gain rises across the
    # video, which is exactly the "volume increases after the middle" effect.
    filter_parts.append(
        f"{amix_in}amix=inputs={len(inputs)}:duration=first:normalize=0"
        f":dropout_transition=0[aout]")

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
#: Word-count targets per bucket, calibrated against the app's existing 15-20s
#: baseline (65-85 words there implies ~4.3 spoken words/sec at this TTS voice
#: speed). "Standard" is the new default: 2026 short-form research puts peak
#: retention for most niches at 25-35s, not the 15-20s this app previously
#: hardcoded everywhere.
DURATION_PRESETS = {
    "Quick (15-20s)": (65, 85, "15-20"),
    "Standard (25-35s)": (110, 145, "25-35"),
}
DEFAULT_DURATION_PRESET = "Standard (25-35s)"


def generate_ollama_script(prompt: str, model: str, hook_style: str = "None (Direct Prompt)",
                           enable_search: bool = False, art_style: str = "Photorealistic",
                           duration_preset: str = DEFAULT_DURATION_PRESET):
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
            
    min_words, max_words, seconds_label = DURATION_PRESETS.get(
        duration_preset, DURATION_PRESETS[DEFAULT_DURATION_PRESET])

    # Stage 1: Creative Story / Script Writer (Free-form text)
    storyteller_system = (
        "You are a world-class short-form video scriptwriter for YouTube Shorts, Instagram Reels "
        f"and TikTok whose videos routinely go viral. Write a punchy ~{seconds_label}-second voiceover "
        "script about the given topic.\n"
        "VIRAL RULES (follow all):\n"
        "- HOOK FIRST: The opening sentence is the single highest-leverage line in the whole script -- "
        "most viewers decide to keep watching or swipe away within the first 1-3 seconds. It must be "
        "EXACTLY 8-14 words (a viewer reads/hears this in under 3 seconds; longer and you've already "
        "lost the swipe decision). Use a bold contrarian claim, a specific common mistake, a shocking "
        "fact, or a curiosity gap. Never open with 'In this video', 'Today', or a slow intro.\n"
        "- OPEN LOOP: Tease something the viewer only fully understands at the end, so they keep watching.\n"
        "- PACING: Short, punchy, spoken-style sentences (each about 6-12 words) that read cleanly as "
        "on-screen captions. One idea per sentence.\n"
        "- ESCALATE: Each sentence should raise curiosity, tension, or stakes more than the last.\n"
        "- PAYOFF + CTA: Land a satisfying payoff, then end with a punchy call to action that tells the "
        "viewer to SUBSCRIBE for more (e.g. 'Subscribe so you never miss one').\n"
        "- Be specific and accurate about the topic; no vague filler or repetition.\n"
        "- Do NOT repeat any sentence or phrase; every line must add new information.\n"
        f"Total length about {min_words}-{max_words} words (about {seconds_label} seconds spoken). "
        "Output ONLY the raw narration text - no scene numbers, brackets, speaker names, emojis, or stage directions."
    )
    
    storyteller_prompt = (
        f"System: {storyteller_system}\n{grounding_info}\n"
        f"User: Write a {seconds_label}-second viral story about: {prompt}."
    )
    if hook_instruction:
        storyteller_prompt += f" Hook Instruction: {hook_instruction}"
        
    payload1 = {
        "model": model,
        "prompt": storyteller_prompt,
        "stream": False
    }

    def _attempt_story():
        # Generous timeout for cloud models; they are slow but usually succeed on retry.
        r = requests.post(url, json=payload1, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:150]}")
        t = (r.json().get("response", "") or "").strip()
        # A real ~15-20s script is ~55-80 words. Reject short/empty output so we
        # NEVER fall back to narrating the bare topic title (which caused the
        # 7-second, fragmented, repeating-caption video).
        if len(t.split()) < 30:
            raise RuntimeError(f"story too short ({len(t.split())} words)")
        return t

    try:
        story_text = retry_call(_attempt_story, attempts=3, base_delay=2.0,
                                label="story text", logger=print)
        print(f"--- Generated Cohesive Story ---\n{story_text}\n---------------------------------")
    except Exception as e:
        raise RuntimeError(
            f"Script generation failed for '{prompt}': the model did not return a usable story ({e}). "
            f"Ensure Ollama and model '{model}' are reachable and responsive."
        )
        
    # Stage 2: Storyboarder & Scene Segmenter (Strict JSON)
    storyboarder_system = (
        "You are an expert viral short-form video editor and storyboarder. Split the provided story "
        "into exactly 7 sequential scenes that will be rendered as a fast-paced vertical 9:16 reel "
        "with word-by-word captions, subtle zoom (Ken Burns) motion, and whoosh transitions between scenes.\n"
        "To keep the video visually consistent (not a set of unrelated random images), you MUST define:\n"
        "1. 'global_visual_style': the overall medium, art style, camera/lighting and color palette "
        "(e.g. 'cinematic photoreal, dramatic lighting, shallow depth of field, rich color grade, high detail').\n"
        "2. 'global_subject_focus': the main character/subject/object that stays CONSTANT across every scene, "
        "described concretely and tied to the topic (e.g. for a goalkeeper: 'an athletic goalkeeper in a red and "
        "black kit with padded gloves'). Never use a generic placeholder unrelated to the topic.\n"
        "3. 'background_music_style': choose ONE of Cinematic, Upbeat, Mysterious, Ambient that best fits the mood.\n"
        "For each scene:\n"
        "1. 'narration': extract a short, caption-friendly segment of the story (about 6-12 words). Keep the story's exact wording and order; do not invent new facts.\n"
        "2. 'speaker': pick one consistent name from: Sarah, Bella, Nicole, Sky, Alloy, Kore, River, Adam, Michael, Fenrir, Puck, Echo, Liam, Onyx, Emma, Isabella, George, Lewis (use the SAME speaker for the whole video unless the story has distinct characters).\n"
        "3. 'visual_prompt': a vivid, specific scene description - the action, emotion, pose, or setting for THIS line, "
        "with a clear focal subject and sense of motion/energy so the zoom and cut land well. It is combined with the "
        "global style and subject, so describe only what changes this scene. Scene 1 should be the most striking, "
        "scroll-stopping visual. No on-screen text, watermarks, camera frames, phone frames, or device frames.\n"
        "4. 'visual_source': 'stock' if this shot could be FILMED in the real world (people, animals, "
        "cities, nature, weather, hands, food, labs, machinery, sports), or 'generate' if it could not "
        "possibly be filmed (inside a black hole, the year 3000, a stick figure, an abstract concept, "
        "a microscopic or cosmic view no camera could capture). Prefer 'stock' whenever it is plausible - "
        "real footage always looks more believable than an AI image.\n"
        "5. 'stock_query': ONLY when visual_source is 'stock'. Two to four PLAIN search keywords for a "
        "stock video library - concrete nouns only, no adjectives, no camera or lighting words. "
        "Good: 'stormy ocean waves', 'scientist microscope lab'. Bad: 'a lone figure silhouetted "
        "against dramatic cinematic light'.\n\n"
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
        "      \"visual_prompt\": \"Specific action, pose, or background setting representing the scene's narration.\",\n"
        "      \"visual_source\": \"stock\",\n"
        "      \"stock_query\": \"two to four plain search keywords\"\n"
        "    },\n"
        "    ... (exactly 7 scenes)\n"
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
    
    # Steer the storyboard's visual anchors toward the chosen art style. For
    # non-photoreal styles (e.g. stickman) this stops the LLM from defaulting to
    # a "cinematic photoreal" global_visual_style that the validator would then
    # have to fight.
    style_directive = ""
    if art_style == "Stickman Animation":
        style_directive = (
            "\n\nIMPORTANT RENDER STYLE: This video is a simple black-and-white STICKMAN animation "
            "(classic stick figures, like 'Animator vs Animation'). Make 'global_subject_focus' a single "
            "consistent stick figure described simply (round circle head, straight thin line limbs, no "
            "detailed features). Make 'global_visual_style' stickman line art (black stick figures, bold "
            "clean lines, plain white background, 2D flat). Each 'visual_prompt' should describe the stick "
            "figure's pose/action for that scene. Do NOT describe anything as photoreal, detailed, or cinematic."
        )

    storyboarder_prompt = f"System: {storyboarder_system}{style_directive}\nStory to segment:\n{story_text}"

    payload2 = {
        "model": model,
        "prompt": storyboarder_prompt,
        "stream": False,
        "format": "json"
    }

    # Stage 2 is the flaky step (cloud models time out / return slightly-off JSON).
    # Retry it, accept a reasonable scene count, and normalize to exactly 7.
    def _attempt_storyboard():
        # Generous timeout: cloud models are slow at large JSON generations.
        r = requests.post(url, json=payload2, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:150]}")
        data = json.loads(clean_json_response(r.json().get("response", "").strip()))
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or len(scenes) < 4:
            raise RuntimeError(f"invalid storyboard (got {len(scenes) if isinstance(scenes, list) else 'no'} scenes)")
        return data

    try:
        data = retry_call(_attempt_storyboard, attempts=2, base_delay=2.0,
                          label="storyboard JSON", logger=print)
        data["scenes"] = normalize_scene_count(data["scenes"], story_text, 7)
        # Make sure the global anchors exist and are tied to the actual topic.
        if not data.get("global_subject_focus"):
            data["global_subject_focus"] = data.get("topic") or prompt
        default_style = ("realistic vertical 9:16, cinematic lighting, dramatic mood, high detail"
                         if art_style == "Photorealistic"
                         else "vertical 9:16")
        data.setdefault("global_visual_style", default_style)
        data.setdefault("topic", prompt)
        return data
    except Exception as e:
        # On failure, build the storyboard from the ACTUAL story so it stays on-topic
        # (the old behavior returned canned, topic-irrelevant filler).
        print(f"Storyboard JSON failed after retries ({e}); building topic-relevant fallback from the story.")
        return build_storyboard_from_story(story_text, prompt)


def generate_validated_script(prompt, model, hook_style="None (Direct Prompt)",
                              enable_search=False, attempts=2, log=print,
                              art_style="Photorealistic",
                              duration_preset=DEFAULT_DURATION_PRESET):
    """Generate a script and run it through the deterministic viral checker.

    Regenerates on HARD failures (off-topic, repeats, wrong length, fallback,
    a hook that runs long...), auto-fixes SOFT issues (missing CTA, non-realistic
    style), and raises if it still cannot produce a valid script - so a broken
    video never reaches render.
    """
    min_words, max_words, _label = DURATION_PRESETS.get(
        duration_preset, DURATION_PRESETS[DEFAULT_DURATION_PRESET])
    last_hard = ["unknown error"]
    for attempt in range(1, attempts + 1):
        try:
            data = generate_ollama_script(prompt, model, hook_style, enable_search=enable_search,
                                          art_style=art_style, duration_preset=duration_preset)
        except Exception as e:
            last_hard = [f"generation error: {e}"]
            log(f"[validator] attempt {attempt}/{attempts}: {last_hard[0]}")
            continue

        hard, soft = validate_script(data, prompt, art_style=art_style,
                                     min_words=min_words, max_words=max_words)
        if not hard:
            if soft:
                log(f"[validator] auto-fixing soft issues: {soft}")
            return autofix(data, art_style=art_style)  # enforce style + ensure CTA
        last_hard = hard
        log(f"[validator] attempt {attempt}/{attempts} rejected (regenerating): {hard}")

    raise RuntimeError(
        f"Script failed viral validation after {attempts} attempts for '{prompt}': {last_hard}"
    )


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
    """Generate one image via Leonardo. Raises RuntimeError with the real API
    error (e.g. 'not enough api tokens') so failures are diagnosable instead of
    being silently swallowed."""
    if not LEONARDO_API_KEY:
        raise RuntimeError("LEONARDO_API_KEY is not set in the environment.")
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

    response = requests.post(url, json=payload, headers=headers, timeout=20)
    if response.status_code != 200:
        # Surface the actual reason: bad key (401), no API credits (400
        # 'not enough api tokens'), rate limit (429), etc.
        raise RuntimeError(f"Leonardo image API HTTP {response.status_code}: {response.text[:300]}")

    generation_id = response.json().get("sdGenerationJob", {}).get("generationId")
    if not generation_id:
        raise RuntimeError(f"Leonardo image API returned no generationId: {response.text[:300]}")

    poll_url = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"
    for _ in range(30):
        time.sleep(2)
        poll_resp = requests.get(poll_url, headers=headers, timeout=10)
        if poll_resp.status_code == 200:
            gen_data = poll_resp.json().get("generations_by_pk", {})
            status = gen_data.get("status")
            if status == "COMPLETE":
                images = gen_data.get("generated_images", [])
                if images:
                    image_url = images[0].get("url")
                    image_id = images[0].get("id")
                    img_data = requests.get(image_url).content
                    out_path = os.path.abspath(os.path.join("temp", f"scene_{int(time.time())}_{image_id[:8]}.png"))
                    with open(out_path, "wb") as f:
                        f.write(img_data)
                    # Leonardo also tops out below the delivery frame, so it gets
                    # the same controlled upscale as the other providers.
                    image_providers.upscale_to_delivery(out_path)
                    return out_path, image_id
                raise RuntimeError("Leonardo generation completed but returned no images.")
            elif status == "FAILED":
                raise RuntimeError("Leonardo generation reported status FAILED.")
    raise RuntimeError("Leonardo image generation timed out while polling for completion.")

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
    response = requests.post(url, json=payload, headers=headers, timeout=20)
    if response.status_code != 200:
        raise RuntimeError(f"Leonardo motion API HTTP {response.status_code}: {response.text[:300]}")
    generation_id = response.json().get("motionGenerationJob", {}).get("generationId")
    if not generation_id:
        raise RuntimeError(f"Leonardo motion API returned no generationId: {response.text[:300]}")
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
                    out_path = os.path.abspath(os.path.join("temp", f"motion_{int(time.time())}.mp4"))
                    with open(out_path, "wb") as f:
                        f.write(vid_data)
                    return out_path
                raise RuntimeError("Leonardo motion completed but returned no video.")
            elif status == "FAILED":
                raise RuntimeError("Leonardo motion reported status FAILED.")
    raise RuntimeError("Leonardo motion generation timed out while polling.")

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


class QualityOptions(BaseModel):
    """Render-quality and retention knobs shared by every render endpoint.

    Kept in one place so the one-shot pipeline and the storyboard re-render
    cannot drift apart and produce visibly different files from the same
    storyboard.
    """
    quality: str = vq.DEFAULT_QUALITY
    motion_style: str = "Dynamic"      # Dynamic | Subtle | Off
    progress_bar: bool = True
    normalize_audio: bool = True
    duck_music: bool = True
    enable_thumbnail: bool = True
    visual_source_mode: str = "Smart Mix"   # Smart Mix | Real Footage Only | AI Only
    subscribe_overlay: bool = True
    channel_handle: str = ""


def quality_kwargs(req: BaseModel) -> dict:
    """Extract the QualityOptions fields from a request for the pipeline call."""
    return {name: getattr(req, name)
            for name in QualityOptions.model_fields
            if hasattr(req, name)}


class ShortRequest(QualityOptions):
    prompt: str
    model: str
    hook_style: str = "None (Direct Prompt)"
    visual_mode: str = "Cinematic Slideshow"  # Cinematic Slideshow, Leonardo Motion Video, or Hailuo Animated Video
    art_style: str = "Photorealistic"  # Photorealistic or Stickman Animation
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
    enable_transition_sfx: bool = False   # off by default: the stock whoosh reads as noise, not a transition

class UploadRequest(BaseModel):
    video_path: str
    platforms: List[str]  # e.g. ["youtube", "instagram"]
    youtube_title: Optional[str] = ""
    youtube_description: Optional[str] = ""
    youtube_tags: Optional[List[str]] = []
    youtube_privacy: Optional[str] = "private"
    instagram_caption: Optional[str] = ""


#: Models that only run generation, not embeddings -- an embedding model in the
#: dropdown produces a confusing failure rather than a script.
_NON_GENERATIVE = ("embed",)


def get_ollama_models():
    """Available Ollama models, locally-runnable ones first.

    Ordering matters because the UI selects the first entry by default. This
    previously force-pinned a *cloud* model to the front, so a exhausted weekly
    quota made every manual draft fail on a model the user never chose. Ollama
    reports cloud models with size 0, which is what separates the two.
    """
    entries = []
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if r.status_code == 200:
            entries = r.json().get("models", [])
    except Exception:
        pass

    local, cloud = [], []
    for m in entries:
        name = m.get("name", "")
        if not name or any(x in name.lower() for x in _NON_GENERATIVE):
            continue
        (local if (m.get("size") or 0) > 0 else cloud).append(name)

    # Largest local model first: on a single machine, size is the best available
    # proxy for output quality, and the default should be the best that works
    # without a network round-trip or a quota.
    local.sort(key=lambda n: next(
        (e.get("size", 0) for e in entries if e.get("name") == n), 0), reverse=True)

    models = local + cloud
    for fallback in ["minimax-m3:cloud", "deepseek-v4-pro:cloud",
                     "gemma4:31b-cloud", "gpt-oss:120b-cloud"]:
        if fallback not in models:
            models.append(fallback)
    return models

# API Endpoints
@app.get("/api/config")
def get_config():
    ollama_models = get_ollama_models()

    return {
        "voices": list(KOKORO_VOICES.keys()),
        "leonardo_models": list(LEONARDO_MODELS.keys()),
        "aspect_ratios": list(ASPECT_RATIO_DIMENSIONS.keys()),
        "music_presets": ["None", "Procedural Ambient"] + list(MUSIC_PRESETS.keys()),
        "satisfying_presets": ["None"] + list(SATISFYING_PRESETS.keys()),
        "viral_hooks": list(VIRAL_HOOKS.keys()),
        "duration_presets": list(DURATION_PRESETS.keys()),
        "default_duration_preset": DEFAULT_DURATION_PRESET,
        "ollama_models": ollama_models,
        "art_styles": list(ART_STYLE_PRESETS.keys()),
        "visual_modes": ["Cinematic Slideshow", "Leonardo Motion Video", "Hailuo Animated Video"],
        "quality_presets": list(vq.QUALITY_PRESETS.keys()),
        "default_quality": vq.DEFAULT_QUALITY,
        "motion_styles": ["Dynamic", "Subtle", "Off"],
        "visual_source_modes": list(VISUAL_SOURCE_MODES),
        "stock_available": bool(stock_footage.get_api_key()),
        "delivery": {
            "fps": vq.FPS,
            "resolution": f"{vq.SHORT_W}x{vq.SHORT_H}",
            "target_lufs": vq.TARGET_LUFS,
        },
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

#: How each scene's visuals are sourced.
VISUAL_SOURCE_MODES = ("Smart Mix", "Real Footage Only", "AI Only")


def use_stock_for_scene(scene: dict, mode: str) -> bool:
    """Decide whether this scene should be filled with real stock footage.

    ``Smart Mix`` honours the ``visual_source`` tag the storyboarder writes per
    scene: real footage for anything filmable, generation for shots that cannot
    exist (inside a black hole, a stick figure, the year 3000). Scenes from
    older storyboards carry no tag, so they default to stock only when they have
    an explicit ``stock_query`` -- otherwise nothing about existing saved
    storyboards changes behaviour.
    """
    if mode == "AI Only":
        return False
    if mode == "Real Footage Only":
        return True
    tag = (scene.get("visual_source") or "").strip().lower()
    if tag in ("stock", "footage", "real"):
        return True
    if tag in ("generate", "generated", "ai"):
        return False
    return bool(scene.get("stock_query"))


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
    enable_transition_sfx: bool = False,
    custom_storyboard: Optional[List[dict]] = None,
    custom_script_data: Optional[dict] = None,
    on_scene_complete=None,
    log_callback=None,
    generation_id: Optional[str] = None,
    caption_sync: bool = True,
    image_provider: Optional[str] = None,
    subscribe_overlay: bool = True,
    channel_handle: str = "",
    art_style: str = "Photorealistic",
    quality: str = vq.DEFAULT_QUALITY,
    motion_style: str = "Dynamic",
    progress_bar: bool = True,
    normalize_audio: bool = True,
    duck_music: bool = True,
    enable_thumbnail: bool = True,
    visual_source_mode: str = "Smart Mix"
):
    """
    Core automated multi-scene viral shorts pipeline.
    Supports rendering directly from custom storyboards and multi-voice configuration.

    Reliability:
      * Per-scene asset generation (image, motion, speech) is retried with
        exponential backoff before the whole render is abandoned.
      * Scenes that already carry an existing ``image_path`` / ``audio_path`` are
        reused, so re-running a partially-failed render resumes instead of
        regenerating everything.
      * ``on_scene_complete(storyboard)`` is invoked after each scene so callers
        can persist partial progress (enabling resume on the next attempt).
      * ``log_callback(msg)`` receives human-readable progress lines.
    """
    _log = log_callback or print
    # 1. Script
    if custom_script_data:
        script_data = custom_script_data
        scenes = script_data.get("scenes", [])
    elif custom_storyboard:
        scenes = custom_storyboard
        script_data = {"scenes": scenes}
    else:
        script_data = generate_validated_script(prompt, model, hook_style, enable_search=enable_search, log=_log, art_style=art_style)
        scenes = script_data.get("scenes", [])
    
    bg_music_path = download_music_preset(music_style) if music_style != "None" else None

    # Budget guard: refuse the render up-front if it would blow today's ceiling.
    # Only scenes still needing a fresh image (i.e. not resumed) incur new cost.
    scenes_needing_image = sum(
        1 for s in scenes
        if not (s.get("image_path") and os.path.exists(s.get("image_path", "")))
    )
    est_cost = cost_tracker.estimate_render_cost(scenes_needing_image, visual_mode)
    cost_tracker.assert_within_budget(est_cost)

    scene_videos = []
    scene_audios = []
    storyboard = []

    # Shared across every scene in THIS video so the same stock clip is never
    # shown twice -- overlapping queries ("deep ocean" / "underwater") and the
    # generic backdrop fallback (which always resolved to one identical clip)
    # both used to produce repeated footage inside a single short.
    used_clip_ids = set()
    # Stable per-generation, so a re-render of the same video reproduces its
    # footage, while a *different* video on the same topic picks differently
    # instead of recycling identical clips.
    # hashlib, not hash(): Python randomises string hashing per process
    # (PYTHONHASHSEED), so hash() would pick different footage on every restart
    # and the "same generation reproduces its footage" property would be a lie.
    variety_seed = (
        int(hashlib.sha256(generation_id.encode()).hexdigest()[:8], 16)
        if generation_id else None
    )

    for idx, scene in enumerate(scenes):
        sc_text = scene["narration"]
        sc_visual_prompt = scene["visual_prompt"]
        
        # Combine scene prompt with global visual style and subject if present
        global_style = script_data.get("global_visual_style", "") if script_data else ""
        global_subject = script_data.get("global_subject_focus", "") if script_data else ""
        final_visual_prompt = script_utils.compose_image_prompt(
            subject=global_subject, scene=sc_visual_prompt, style=global_style)
        
        # Pick speaker voice
        if not custom_storyboard and not custom_script_data:
            sc_voice_key = voice
        else:
            sc_speaker = scene.get("speaker", voice)
            sc_voice_key = map_speaker_to_voice_key(sc_speaker) if isinstance(sc_speaker, str) else voice
        
        # Synthesize voice if audio doesn't exist (resume: reuse existing audio)
        sc_audio = scene.get("audio_path")
        if not sc_audio or not os.path.exists(sc_audio):
            def _gen_speech():
                a, err = generate_speech_audio(sc_text, sc_voice_key, speed, "Normal")
                if not a:
                    raise RuntimeError(f"voice synthesis returned nothing: {err}")
                return a
            sc_audio = retry_call(
                _gen_speech, attempts=3, base_delay=2.0,
                label=f"speech scene {idx+1}", logger=_log
            )
        else:
            _log(f"Scene {idx+1}: reusing existing audio (resume).")

        info = sf.info(sc_audio)
        sc_duration = info.duration
        scene_audios.append(sc_audio)

        # Real footage first. A filmed person has no anatomy for a model to get
        # wrong, and Pexels serves vertical clips at or above delivery size, so
        # this path also skips the upscale that softens generated stills.
        sc_clip = scene.get("clip_path")
        if sc_clip and os.path.exists(sc_clip):
            _log(f"Scene {idx+1}: reusing existing stock clip (resume).")
        elif use_stock_for_scene(scene, visual_source_mode):
            query = scene.get("stock_query") or sc_visual_prompt
            dest = os.path.abspath(
                os.path.join("temp", f"scene_stock_{int(time.time() * 1000)}_{idx}.mp4"))
            sc_clip = stock_footage.fetch_clip(
                query, dest,
                global_focus=script_data.get("global_subject_focus", "") if script_data else "",
                orientation=stock_footage.PORTRAIT,
                min_height=vq.SHORT_H,
                used_ids=used_clip_ids,
                variety_seed=variety_seed,
                log=_log,
            )
            if sc_clip:
                scene["clip_path"] = sc_clip
                _log(f"Scene {idx+1}: using real footage for '{query}'.")
            else:
                # Every stock fallback missed. Generating is still better than
                # failing the render.
                _log(f"Scene {idx+1}: no stock match for '{query}'; generating instead.")
        else:
            sc_clip = None

        # Generate Image if not exists (resume: reuse existing image)
        sc_img = scene.get("image_path")
        image_id = scene.get("image_id")
        if sc_clip:
            pass  # Real footage won; no image needed for this scene.
        elif not sc_img or not os.path.exists(sc_img):
            # Dispatch to the configured image provider. Each backend raises a
            # descriptive error on failure, so the real reason reaches the logs.
            def _dispatch_image(p):
                prov = image_providers.resolve_provider(image_provider)
                if prov == "leonardo":
                    return generate_leonardo_image(p, leonardo_model, "9:16")
                # Ask for the delivery frame size. Each provider generates at
                # whatever it can actually do well and upscales from there, so
                # the Ken Burns stage never has to blow up a tiny frame.
                return image_providers.generate_image(
                    prov, p, image_providers.DELIVERY_W, image_providers.DELIVERY_H)

            img_res = retry_call(
                lambda: _dispatch_image(final_visual_prompt),
                attempts=3, base_delay=3.0,
                label=f"image scene {idx+1}", logger=_log
            )
            sc_img, image_id = img_res
            if image_providers.resolve_provider(image_provider) == "leonardo":
                cost_tracker.record(generation_id, "image")
        else:
            _log(f"Scene {idx+1}: reusing existing image (resume).")

        scene_video_path = os.path.abspath(os.path.join("temp", f"scene_vid_{int(time.time())}_{idx}.mp4"))

        # Make video segment (slideshow with zoompan or motion video)
        motion_vid_path = None
        if visual_mode == "Leonardo Motion Video" and image_id:
            # Motion is best-effort: retry, but fall back to slideshow if it never succeeds.
            try:
                motion_vid_path = retry_call(
                    lambda: generate_leonardo_motion(image_id, final_visual_prompt),
                    attempts=2, base_delay=4.0,
                    label=f"motion scene {idx+1}", logger=_log
                )
                if motion_vid_path:
                    cost_tracker.record(generation_id, "motion")
            except RetryError:
                _log(f"Scene {idx+1}: motion generation failed; falling back to slideshow.")
                motion_vid_path = None
        elif visual_mode == "Hailuo Animated Video":
            # Animate the scene image (e.g. a stickman frame) into a short clip.
            # Best-effort: retry, then fall back to slideshow if it never succeeds.
            try:
                motion_vid_path = retry_call(
                    lambda: generate_hailuo_video(final_visual_prompt, first_frame_path=sc_img),
                    attempts=2, base_delay=5.0,
                    label=f"hailuo scene {idx+1}", logger=_log
                )
                if motion_vid_path:
                    cost_tracker.record(generation_id, "motion")
            except RetryError:
                _log(f"Scene {idx+1}: Hailuo generation failed; falling back to slideshow.")
                motion_vid_path = None

        source_clip = sc_clip or motion_vid_path
        if source_clip:
            # -stream_loop -1 with -t handles both cases: a clip shorter than the
            # narration loops, a longer one is trimmed. Stock gets the same grade
            # as generated scenes so a mixed reel reads as one video rather than
            # two sources stitched together.
            grade = vq.stock_grade() if sc_clip else ""
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-fflags", "+genpts", "-stream_loop", "-1",
                "-i", source_clip, "-t", str(sc_duration),
                "-vf", (f"scale={vq.SHORT_W}:{vq.SHORT_H}:force_original_aspect_ratio=increase,"
                        f"crop={vq.SHORT_W}:{vq.SHORT_H},fps={vq.FPS}{grade},setsar=1"),
            ] + vq.intermediate_encode_args() + [scene_video_path]
        else:
            # Cinematic slideshow. Scene 1 is flagged as the hook so it gets the
            # harder, faster push that has to earn the first second.
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", sc_img, "-t", str(sc_duration),
                "-vf", vq.ken_burns_vf(idx, sc_duration, is_hook=(idx == 0),
                                       motion_style=motion_style),
            ] + vq.intermediate_encode_args() + [scene_video_path]

        vq.run_ffmpeg(ffmpeg_cmd, label=f"scene {idx+1} video")
        scene_videos.append(scene_video_path)
        
        aud_rel = os.path.relpath(sc_audio, os.path.abspath(os.path.curdir))
        scene_entry = {
            "scene": idx + 1,
            "speaker": sc_speaker,
            "narration": sc_text,
            "visual_prompt": final_visual_prompt,
            "image_id": image_id,
            "audio_url": f"http://localhost:8000/{aud_rel.replace(os.path.sep, '/')}",
            "audio_path": sc_audio,
            "duration": sc_duration,
            "visual_source": "stock" if sc_clip else "generated",
        }
        # A stock scene has a clip and no still; the editor previews whichever
        # one exists, so only the populated key is emitted.
        if sc_clip:
            clip_rel = os.path.relpath(sc_clip, os.path.abspath(os.path.curdir))
            scene_entry["clip_path"] = sc_clip
            scene_entry["clip_url"] = f"http://localhost:8000/{clip_rel.replace(os.path.sep, '/')}"
        if sc_img:
            img_rel = os.path.relpath(sc_img, os.path.abspath(os.path.curdir))
            scene_entry["image_path"] = sc_img
            scene_entry["image_url"] = f"http://localhost:8000/{img_rel.replace(os.path.sep, '/')}"
        storyboard.append(scene_entry)

        # Write asset paths back into the source scene so a re-run resumes.
        if sc_img:
            scene["image_path"] = sc_img
        if sc_clip:
            scene["clip_path"] = sc_clip
        scene["image_id"] = image_id
        scene["audio_path"] = sc_audio

        # Persist partial progress so a failed render can resume from here.
        if on_scene_complete:
            try:
                on_scene_complete(list(storyboard))
            except Exception as cb_err:  # noqa: BLE001 - progress persistence is best-effort
                _log(f"Scene {idx+1}: progress persistence failed: {cb_err}")

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
        
    # Generate procedural music if selected
    if music_style == "Procedural Ambient":
        try:
            print("Generating procedural music in real-time...")
            info = sf.info(merged_audio)
            audio_duration = info.duration
            bg_music_path = os.path.abspath(os.path.join("temp", f"procedural_music_{timestamp}.wav"))
            from music_generator import write_procedural_music
            write_procedural_music(audio_duration, bg_music_path)
            print(f"Procedural music generated: {bg_music_path}")
        except Exception as e:
            print(f"Error generating procedural music: {e}")
            bg_music_path = None
        
    # Mix Audio (Speech + BG Music). The music is sidechain-ducked under the
    # narration rather than parked at a fixed level, so it fills the gaps
    # without ever competing with the voice.
    audio_mixed = os.path.abspath(os.path.join("temp", f"audio_mixed_{timestamp}.wav"))
    if bg_music_path and os.path.exists(bg_music_path):
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_audio, "-stream_loop", "-1", "-i", bg_music_path,
            "-filter_complex", vq.music_mix_filter(duck=duck_music),
            "-map", "[aout]", "-c:a", "pcm_s16le", audio_mixed
        ]
        vq.run_ffmpeg(ffmpeg_cmd, label="music mix")
    else:
        shutil.copy(merged_audio, audio_mixed)

    # Mix transition SFX into audio_mixed
    transition_times = []
    curr_t = 0.0
    for sc in storyboard[:-1]:
        curr_t += sc["duration"]
        transition_times.append(curr_t)

    audio_sfx_mixed = os.path.abspath(os.path.join("temp", f"audio_sfx_mixed_{timestamp}.wav"))
    if enable_transition_sfx:
        mix_transition_sfx(audio_mixed, audio_sfx_mixed, transition_times)
    else:
        shutil.copy(audio_mixed, audio_sfx_mixed)

    # Normalize last, once every element is in the mix. Delivering at -14 LUFS
    # means YouTube's own normalizer leaves the track alone instead of pushing a
    # quiet mix up and dragging its noise floor along with it.
    audio_final_mixed = os.path.abspath(os.path.join("temp", f"audio_final_mixed_{timestamp}.wav"))
    if normalize_audio:
        vq.normalize_loudness(audio_sfx_mixed, audio_final_mixed, log=_log)
    else:
        shutil.copy(audio_sfx_mixed, audio_final_mixed)

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
            "-shortest",
        ] + vq.intermediate_encode_args() + vq.audio_encode_args() + [processed_video]
        vq.run_ffmpeg(ffmpeg_cmd, label="split-screen composite")
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", merged_video, "-i", audio_final_mixed, "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
        ] + vq.audio_encode_args() + [processed_video]
        vq.run_ffmpeg(ffmpeg_cmd, label="mux audio")

    # Burn-in pass. Subtitles, the retention progress bar and the SUBSCRIBE CTA
    # all go on in ONE encode: each used to be its own ffmpeg run, so a finished
    # video had been through three generations of lossy re-encoding before it
    # was ever uploaded.
    final_rendered_video = os.path.abspath(os.path.join("outputs", f"viral_reel_{timestamp}.mp4"))
    total_dur = sum(float(sc.get("duration", 0) or 0) for sc in storyboard)
    ass_path = None
    if enable_captions:
        ass_path = os.path.abspath(os.path.join("temp", f"subtitles_{timestamp}.ass"))
        align = 2

        # Prefer Whisper word-level timing (synced to the actual voice); the legacy
        # length-proportional estimate is the fallback if Whisper is unavailable.
        captions_written = False
        if caption_sync:
            try:
                from transcribe import transcribe_words
                import captions as captions_mod
                words = transcribe_words(merged_audio)
                if words:
                    captions_mod.write_ass_from_words(
                        words, ass_path, font_name=caption_font, font_size=caption_size,
                        margin_v=caption_margin_v, alignment=align,
                        highlight_color=caption_color, style_mode=caption_style
                    )
                    captions_written = True
                    _log(f"Captions synced to audio via Whisper ({len(words)} words).")
            except Exception as cap_err:  # noqa: BLE001 - degrade gracefully
                _log(f"Whisper caption sync unavailable ({cap_err}); using estimated timing.")

        if not captions_written:
            generate_ass_subtitles(
                storyboard, ass_path, caption_font, caption_size,
                margin_v=caption_margin_v, alignment=align, highlight_color=caption_color,
                style_mode=caption_style
            )

    finish_filter = vq.build_finish_filter(
        subtitles_path=ass_path,
        total_duration=total_dur,
        subscribe=subscribe_overlay,
        channel_handle=channel_handle,
        progress_bar=progress_bar,
    )

    if finish_filter:
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", processed_video, "-vf", finish_filter,
        ] + vq.video_encode_args(quality) + ["-c:a", "copy", final_rendered_video]
        vq.run_ffmpeg(ffmpeg_cmd, label="final burn-in")
        _log(f"Burned in captions/overlays in a single {quality} pass.")
    else:
        # Nothing to draw, but the file still needs the delivery encode
        # (faststart in particular) rather than a straight copy.
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", processed_video,
        ] + vq.video_encode_args(quality) + ["-c:a", "copy", final_rendered_video]
        vq.run_ffmpeg(ffmpeg_cmd, label="final encode")

    thumbnail_path = None
    if enable_thumbnail:
        title = (script_data.get("youtube_metadata", {}) or {}).get("title") \
            or script_data.get("topic") or prompt
        thumbnail_path = vq.generate_thumbnail(
            final_rendered_video, title,
            os.path.abspath(os.path.join("outputs", f"viral_reel_{timestamp}_thumb.jpg")),
            log=_log,
        )
        if thumbnail_path:
            _log("Generated a title thumbnail for search and suggested feeds.")

    script_data["thumbnail_path"] = thumbnail_path
    return final_rendered_video, storyboard, script_data.get("topic", prompt), script_data


# New Request Models & APIs
class DraftRequest(BaseModel):
    prompt: str
    model: str
    hook_style: str = "None (Direct Prompt)"
    enable_search: bool = False
    voice: Optional[str] = "Sarah (Female - US - Soft)"
    art_style: str = "Photorealistic"
    duration_preset: str = DEFAULT_DURATION_PRESET

class RenderRequest(QualityOptions):
    generation_id: str
    storyboard: List[dict]
    visual_mode: str = "Cinematic Slideshow"
    image_provider: Optional[str] = None  # 'local' | 'pollinations' | 'leonardo'; None -> env default
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
    enable_transition_sfx: bool = False   # off by default: the stock whoosh reads as noise, not a transition

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
        script_data = generate_validated_script(req.prompt, req.model, req.hook_style,
                                                 enable_search=req.enable_search, art_style=req.art_style,
                                                 duration_preset=req.duration_preset)
        scenes = script_data.get("scenes", [])

        # Build initial storyboard structure.
        #
        # This copies the LLM's scene fields forward rather than listing them:
        # the previous version hand-picked only narration and visual_prompt, so
        # `visual_source` and `stock_query` were silently dropped here. The
        # render then found no stock tags and generated every scene with the
        # image provider -- which is why drafting through the UI produced
        # AI-looking video while a hand-tagged storyboard produced real footage.
        storyboard = []
        for idx, scene in enumerate(scenes):
            entry = dict(scene)
            entry.update({
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
            storyboard.append(entry)
            
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
    # Resume: prefer the storyboard persisted in the DB (it may already carry
    # asset paths from a previous partial run) over the request payload.
    storyboard_in = req.storyboard
    existing = db_manager.get_video_generation(generation_id)
    if existing and existing.get("storyboard"):
        persisted = {s.get("scene"): s for s in existing["storyboard"]}
        for sc in storyboard_in:
            prev = persisted.get(sc.get("scene"))
            if prev and not sc.get("image_path"):
                sc["image_path"] = prev.get("image_path")
                sc["image_id"] = prev.get("image_id")
                sc["audio_path"] = prev.get("audio_path")

    # Preserve the global visual anchors (style + recurring subject) saved at
    # draft time so the chosen art style (e.g. stickman) survives to render.
    # Rendering from a bare storyboard would otherwise drop global_visual_style.
    persisted_script = (existing or {}).get("script_data") or {}
    render_script_data = dict(persisted_script)
    render_script_data["scenes"] = storyboard_in

    def _persist_progress(sb):
        db_manager.update_video_generation(generation_id, storyboard=sb)

    try:
        db_manager.update_video_generation(generation_id, status="rendering")

        final_video, storyboard, topic, script_data = run_viral_shorts_pipeline_new(
            prompt="",
            model="",
            visual_mode=req.visual_mode,
            image_provider=req.image_provider,
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
            custom_script_data=render_script_data,
            on_scene_complete=_persist_progress,
            generation_id=generation_id,
            **quality_kwargs(req)
        )

        db_manager.update_video_generation(
            generation_id, storyboard=storyboard, final_video_path=final_video, status="completed"
        )
    except Exception as e:
        print(f"Rendering failed: {e}")
        db_manager.update_video_generation(generation_id, status="failed")
        notify(
            "Storyboard render failed",
            f"Render task for generation {generation_id} failed: {e}",
            context={"generation_id": generation_id, "topic": (existing or {}).get("topic")}
        )

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
            art_style=req.art_style,
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
            enable_transition_sfx=req.enable_transition_sfx,
            generation_id=gen_id,
            **quality_kwargs(req)
        )
        rel_out = os.path.relpath(final_video, os.path.abspath(os.path.curdir))
        
        db_manager.update_video_generation(
            gen_id, topic=topic, script_data=script_data, storyboard=storyboard, final_video_path=final_video, status="completed"
        )
        
        return {
            "success": True,
            "video_url": f"http://localhost:8000/{rel_out.replace(os.path.sep, '/')}",
            "thumbnail_url": static_url(script_data.get("thumbnail_path")),
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

@app.get("/api/image-provider/status")
def get_image_provider_status(provider: Optional[str] = None):
    """Report readiness for an image provider (the given one, or the env default
    when omitted). For 'local' it pings the SD server; for 'leonardo' it checks
    the API key; 'pollinations' is keyless and always available."""
    provider = image_providers.resolve_provider(provider)
    max_w, max_h = image_providers.PROVIDER_MAX.get(provider, (0, 0))
    result = {
        "provider": provider,
        "available": True,
        # What the provider can actually generate, versus the frame we deliver.
        # Anything below delivery size has to be upscaled, and upscaling cannot
        # add detail back -- this is the number that decides image sharpness.
        "max_resolution": f"{max_w}x{max_h}" if max_w else None,
        "delivery_resolution": f"{image_providers.DELIVERY_W}x{image_providers.DELIVERY_H}",
        "upscale_factor": round(image_providers.DELIVERY_W / max_w, 2) if max_w else None,
    }
    if provider == "local":
        base = os.getenv("SD_SERVER_URL", "http://localhost:8001").rstrip("/")
        try:
            r = requests.get(f"{base}/health", timeout=3)
            if r.status_code == 200:
                data = r.json()
                native = data.get("native") or 1024
                result.update({"available": True, "model": data.get("model"),
                               "device": data.get("device"), "loaded": data.get("loaded"),
                               "native": native})
                bucket_w, bucket_h = local_sd_bucket(native)
                result["max_resolution"] = f"{bucket_w}x{bucket_h}"
                result["upscale_factor"] = round(image_providers.DELIVERY_W / bucket_w, 2)
            else:
                result["available"] = False
        except Exception:
            result["available"] = False
    elif provider == "leonardo":
        result["available"] = bool(LEONARDO_API_KEY)
    return result


def local_sd_bucket(native: int = 1024):
    """Vertical bucket the local SD server will actually render at."""
    try:
        import local_sd
        return local_sd.best_bucket(image_providers.DELIVERY_W,
                                    image_providers.DELIVERY_H, native)
    except Exception:  # noqa: BLE001 - diffusers may not be installed
        return (768, 1344) if native >= 1024 else (384, 672)


@app.get("/api/image-provider/models")
def get_local_sd_models():
    """Catalog of free local models, with the tradeoff each one carries.

    Proxied from the SD server when it is up, so the reported "current" model is
    the one that would actually render, not this process's stale env var.
    """
    base = os.getenv("SD_SERVER_URL", "http://localhost:8001").rstrip("/")
    try:
        r = requests.get(f"{base}/models", timeout=3)
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001 - fall back to the local catalog
        pass
    try:
        import local_sd
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"diffusers not installed: {e}")
    return {
        "catalog": [{"name": name, **entry} for name, entry in local_sd.MODEL_CATALOG.items()],
        "current": local_sd.resolve_model(),
        "server_offline": True,
    }


class SelectImageModelRequest(BaseModel):
    model: str


@app.post("/api/image-provider/models/select")
def select_local_sd_model(req: SelectImageModelRequest):
    """Point the local SD server at a different model."""
    base = os.getenv("SD_SERVER_URL", "http://localhost:8001").rstrip("/")
    try:
        r = requests.post(f"{base}/models/select", json={"model": req.model}, timeout=10)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Local SD server unreachable at {base} ({e}). Start it with: python sd_server.py")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()

def video_used_synthetic_media(storyboard) -> bool:
    """True if any scene's visuals came from image generation rather than real
    stock footage -- the trigger for YouTube's "Altered or Synthetic Content"
    disclosure (``status.containsSyntheticMedia``), in full enforcement since
    January 2026. A storyboard with no ``visual_source`` tags at all (older
    generations, predating that field) is treated conservatively as synthetic,
    since the pipeline's only non-stock path was AI image generation.
    """
    scenes = storyboard or []
    if not scenes:
        return False
    return any(s.get("visual_source", "generate") == "generate" for s in scenes)


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
            
        gen_id = job["video_generation_id"]

        if "youtube" in job["platforms"]:
            if db_manager.is_platform_uploaded(gen_id, "youtube"):
                prev = db_manager.get_platform_upload(gen_id, "youtube")
                log_message(f"YouTube: already published (video id {prev['external_id']}); skipping to avoid duplicate.")
            else:
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
                    progress_callback=yt_progress,
                    contains_synthetic_media=video_used_synthetic_media(video_gen.get("storyboard")),
                )
                db_manager.record_platform_upload(gen_id, "youtube", vid_id)
                log_message(f"YouTube upload successful! Video URL: https://youtu.be/{vid_id}")

        if "instagram" in job["platforms"]:
            if db_manager.is_platform_uploaded(gen_id, "instagram"):
                prev = db_manager.get_platform_upload(gen_id, "instagram")
                log_message(f"Instagram: already published (media id {prev['external_id']}); skipping to avoid duplicate.")
            else:
                log_message("Instagram Reels upload starting...")
                ig_meta = job.get("instagram_metadata") or {}

                def ig_progress(msg):
                    log_message(msg)

                media_id = upload_reel_to_instagram(
                    video_file,
                    ig_meta.get("caption", ""),
                    progress_callback=ig_progress
                )
                db_manager.record_platform_upload(gen_id, "instagram", media_id)
                log_message(f"Instagram upload successful! Media ID: {media_id}")

        log_message("Upload process complete!")
        db_manager.update_upload_job(job_id, status="completed", logs=logs)
    except Exception as e:
        log_message(f"Upload failed: {str(e)}")
        db_manager.update_upload_job(job_id, status="failed", logs=logs)
        notify(
            "Upload job failed",
            f"Upload job {job_id} failed: {e}",
            context={"job_id": job_id, "platforms": job.get("platforms")}
        )

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

def viral_agent_scheduler_loop():
    """Background thread that runs the auto-generation agent at scheduled times."""
    print("Starting background viral agent scheduler thread...")
    while True:
        try:
            from viral_agent import load_scheduler_config, save_scheduler_config, run_viral_agent_job
            config = load_scheduler_config()
            
            if config.get("enabled"):
                now = datetime.now()
                current_time_str = now.strftime("%H:%M")  # "HH:MM" format
                current_date_str = now.strftime("%Y-%m-%d") # "YYYY-MM-DD" format
                
                time1 = config.get("time1", "10:00")
                time2 = config.get("time2", "18:00")
                
                last_run_date = config.get("last_run_date", "")
                last_run_slots = config.get("last_run_slots", [])
                
                # Reset slots if it's a new day
                if last_run_date != current_date_str:
                    last_run_date = current_date_str
                    last_run_slots = []
                    config["last_run_date"] = last_run_date
                    config["last_run_slots"] = last_run_slots
                    save_scheduler_config(config)
                
                # Check Slot 1
                if current_time_str >= time1 and "slot1" not in last_run_slots:
                    last_run_slots.append("slot1")
                    config["last_run_slots"] = last_run_slots
                    save_scheduler_config(config)
                    
                    # Trigger in background thread
                    t = threading.Thread(target=run_viral_agent_job, args=(f"Slot 1 ({time1})", config))
                    t.daemon = True
                    t.start()
                    
                # Check Slot 2
                elif current_time_str >= time2 and "slot2" not in last_run_slots:
                    last_run_slots.append("slot2")
                    config["last_run_slots"] = last_run_slots
                    save_scheduler_config(config)
                    
                    # Trigger in background thread
                    t = threading.Thread(target=run_viral_agent_job, args=(f"Slot 2 ({time2})", config))
                    t.daemon = True
                    t.start()
        except Exception as e:
            print(f"Error in viral agent scheduler loop: {e}")
        time.sleep(30)  # Check every 30 seconds

@app.on_event("startup")
def startup_event():
    scheduler_thread = threading.Thread(target=upload_scheduler_loop)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    agent_thread = threading.Thread(target=viral_agent_scheduler_loop)
    agent_thread.daemon = True
    agent_thread.start()

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

# --- Approval gate ---
@app.get("/api/uploads/pending")
def api_get_pending_approvals():
    """Generations held for human review before publishing."""
    return db_manager.get_upload_jobs_by_status("pending_approval")

@app.post("/api/uploads/{job_id}/approve")
def api_approve_upload(job_id: str):
    job = db_manager.get_upload_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    if job["status"] != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Job is not pending approval (status: {job['status']})")
    # Flip to 'scheduled' with a past time so the upload loop picks it up promptly.
    db_manager.update_upload_job(
        job_id, status="scheduled",
        logs=job.get("logs", []) + ["Approved by user; queued for publishing."]
    )
    return {"success": True, "job_id": job_id, "status": "scheduled"}

@app.post("/api/uploads/{job_id}/reject")
def api_reject_upload(job_id: str):
    job = db_manager.get_upload_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    db_manager.update_upload_job(
        job_id, status="rejected",
        logs=job.get("logs", []) + ["Rejected by user; will not be published."]
    )
    return {"success": True, "job_id": job_id, "status": "rejected"}

# --- Analytics feedback loop ---
@app.post("/api/analytics/refresh-youtube")
def api_refresh_youtube_analytics():
    from analytics import refresh_youtube_stats, refresh_youtube_analytics

    def _is_scope_error(msg):
        return "insufficient" in msg.lower() or "scope" in msg.lower() or "not authorized" in msg.lower()

    # Each path needs read scopes the original upload-only token lacks; guard both
    # independently so a missing grant returns a clear re-auth hint, not a 500.
    stats_updated, retention_updated = 0, 0
    errors = {}
    try:
        stats_updated = refresh_youtube_stats().get("updated", 0)
    except Exception as e:
        errors["stats_error"] = str(e)
    try:
        retention_updated = refresh_youtube_analytics().get("updated", 0)
    except Exception as e:
        errors["retention_error"] = str(e)

    needs_reauth = any(_is_scope_error(m) for m in errors.values())
    return {
        "success": not errors,
        "stats_updated": stats_updated,
        "retention_updated": retention_updated,
        **errors,
        "needs_reauth": needs_reauth,
        "hint": ("Re-authenticate YouTube to grant read access (youtube.readonly + "
                 "yt-analytics.readonly), then retry.") if needs_reauth else None,
    }

@app.get("/api/analytics/top")
def api_get_top_performing(limit: int = 5):
    return db_manager.get_top_performing(limit=limit)

@app.get("/api/analytics/retention-leaders")
def api_get_retention_leaders(limit: int = 5):
    return db_manager.get_engagement_leaders(limit=limit)

@app.get("/api/competitor-signals")
def api_competitor_signals(query: str, max_results: int = 10, refresh: bool = True):
    """Mine YouTube for what's hot in a niche *right now*, ranked by view velocity.

    Returns the hottest videos plus an LLM-ready hint about winning patterns.
    Needs the youtube.readonly scope (same re-auth as the analytics loop).
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    query = query.strip()

    import competitor_research
    error = None
    if refresh:
        try:
            competitor_research.store_competitor_videos(query, max_results=max_results)
        except Exception as e:
            error = str(e)

    videos = db_manager.get_top_velocity(query, limit=max_results)
    needs_reauth = bool(error) and ("insufficient" in error.lower() or "scope" in error.lower() or "not authorized" in error.lower())
    return {
        "query": query,
        "videos": videos,
        "hint": competitor_research.get_competitor_hint(query, limit=max_results),
        "error": error,
        "needs_reauth": needs_reauth,
    }

# --- Cost tracking ---
@app.get("/api/costs/today")
def api_get_costs_today():
    budget = cost_tracker.get_daily_budget()
    spent = db_manager.get_spend_today("leonardo")
    return {
        "service": "leonardo",
        "spent_today": spent,
        "daily_budget": budget,
        "remaining": (budget - spent) if budget is not None else None,
    }

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

def static_url(path: Optional[str]) -> str:
    """Turn an on-disk render artifact into a URL the frontend can load."""
    if not path or not os.path.exists(path):
        return ""
    rel = os.path.relpath(path, os.path.abspath(os.path.curdir))
    return f"http://localhost:8000/{rel.replace(os.path.sep, '/')}"


def thumbnail_url_for(video_path: Optional[str]) -> str:
    """URL of the thumbnail both pipelines write beside the finished video.

    Deriving it from the video path keeps the thumbnail available for older
    generations too, without a database migration to store the extra column.
    """
    if not video_path:
        return ""
    return static_url(f"{os.path.splitext(video_path)[0]}_thumb.jpg")


@app.get("/api/generation-status/{generation_id}")
def api_generation_status(generation_id: str):
    gen = db_manager.get_video_generation(generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")

    video_path = gen.get("final_video_path")
    return {
        "status": gen["status"],
        "video_url": static_url(video_path),
        "thumbnail_url": thumbnail_url_for(video_path),
        "storyboard": gen["storyboard"],
        "youtube_metadata": gen.get("script_data", {}).get("youtube_metadata") if gen.get("script_data") else None,
        "instagram_metadata": gen.get("script_data", {}).get("instagram_metadata") if gen.get("script_data") else None,
    }

@app.delete("/api/generation/{generation_id}")
def api_delete_generation(generation_id: str):
    try:
        db_manager.delete_video_generation(generation_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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


@app.get("/api/recommend-topics")
def recommend_topics(geo: str = "US", count: int = 5, model: Optional[str] = None,
                     focus: str = ""):
    """Recommend fresh, non-repeating viral topics for a high-RPM market.

    Subject areas are discovered per call rather than drawn from a fixed list,
    so any subject the model knows about is reachable -- a constant list would
    cap the topic space the same way the old 31-entry curiosity library did.
    Grounded in live Google Trends and Wikipedia signals. Novelty is enforced
    with a hard keyword filter against previously-generated topics, not a
    prompt instruction: the prompt-only approach let five reworded variants of
    the same ocean fact into the library.

    ``focus`` optionally constrains every suggestion to one interest (e.g.
    "cricket", "cooking") for creators working a specific niche.

    Returns {title, rationale, niche, rpm_tier, est_rpm, geo, source}.
    """
    # Lazy import: viral_agent imports from backend at module load (circular).
    from viral_agent import ALLOWED_RPM_GEOS
    import trend_analyser

    geo = (geo or "US").upper()
    if geo not in ALLOWED_RPM_GEOS:
        geo = "US"
    count = max(1, min(count, 8))
    # Default to whatever the scheduler is configured to use, so the UI and the
    # auto-agent stay on the same model instead of this silently pinning a
    # cloud model that may be out of quota.
    if not model:
        try:
            from viral_agent import load_scheduler_config
            model = load_scheduler_config().get("model")
        except Exception:
            model = None
        model = model or "qwen2.5:7b-instruct"

    performance_hint = ""
    exclude_topics = []
    try:
        import analytics
        performance_hint = analytics.get_performance_hint()
    except Exception as e:
        print(f"recommend_topics: performance hint unavailable: {e}")
    try:
        exclude_topics = db_manager.get_recent_topics(40)
    except Exception as e:
        print(f"recommend_topics: recent topics unavailable: {e}")

    try:
        return trend_analyser.analyse(
            geo=geo, model=model, count=count,
            used_topics=exclude_topics,
            performance_hint=performance_hint,
            focus=(focus or "").strip(),
        )
    except Exception as e:
        # Surfaced, not swallowed. The old code fell back to raw Google Trends
        # headlines on any failure, so the UI presented "lindsay clancy trial
        # live" as a curated recommendation with no sign that ranking had died.
        raise HTTPException(
            status_code=502,
            detail=f"Topic analysis failed ({e}). Check that Ollama is running and "
                   f"the model '{model}' is available.")


# Scheduler Config & Logs API
class SchedulerConfigUpdate(BaseModel):
    enabled: bool
    region: str
    time1: str
    time2: str
    model: str
    leonardo_model: str
    voice: str
    privacy: str
    enable_captions: bool
    caption_font: str
    caption_size: int
    caption_margin_v: int
    caption_color: str
    caption_style: str
    topic_source: str = "trends"
    curiosity_category: str = "All"
    # Optional: constrains every auto-generated topic to one interest. Blank
    # keeps the fully open-ended behaviour; set it if you want the channel to
    # reinforce one subject, which research finds builds audience faster than
    # jumping topic every video.
    channel_niche: str = ""
    duration_preset: str = DEFAULT_DURATION_PRESET

@app.get("/api/curiosity-topics")
def get_curiosity_topics():
    """Serve the curated curiosity-topic library (single source of truth shared
    with the auto-agent scheduler) plus the list of categories."""
    from curiosity_topics import CURIOSITY_TOPICS, get_categories
    return {"topics": CURIOSITY_TOPICS, "categories": get_categories()}

@app.get("/api/scheduler/config")
def get_scheduler_config():
    from viral_agent import load_scheduler_config
    return load_scheduler_config()

@app.post("/api/scheduler/config")
def update_scheduler_config(req: SchedulerConfigUpdate):
    from viral_agent import load_scheduler_config, save_scheduler_config
    config = load_scheduler_config()
    config.update(req.dict())
    save_scheduler_config(config)
    return {"success": True, "config": config}

@app.get("/api/scheduler/logs")
def get_scheduler_logs():
    from viral_agent import load_scheduler_logs
    return load_scheduler_logs()

@app.delete("/api/scheduler/logs")
def delete_scheduler_logs():
    from viral_agent import save_scheduler_logs
    save_scheduler_logs([])
    return {"success": True, "message": "Scheduler execution logs cleared."}

@app.post("/api/scheduler/trigger")
def trigger_scheduler_agent(background_tasks: BackgroundTasks):
    from viral_agent import run_viral_agent_job
    background_tasks.add_task(run_viral_agent_job, "Manual Trigger")
    return {"success": True, "message": "Viral Agent run triggered in background."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
