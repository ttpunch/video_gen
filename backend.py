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
from contextlib import asynccontextmanager
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
import llm_client
from script_utils import build_storyboard_from_story, normalize_scene_count
from script_validator import validate_script, autofix, mechanically_fix_hard_issues, ART_STYLE_PRESETS
from search_helper import get_web_grounding_context, clean_json_response
from uploader_youtube import upload_video_to_youtube, is_youtube_authenticated, trigger_youtube_auth_flow_url

# Global in-memory storage for upload job logs
upload_jobs = {}

LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# Measured on this app's actual prompts: the largest realistic call (storyboard
# generation with full history/grounding context) is ~1000 tokens in, under
# 700 out -- comfortably inside 4096 with 2x headroom. Ollama's model default
# is 32768, which on a 16GB Mac allocates a KV cache far bigger than this app
# ever uses: measured directly, capping it here took one model's resident size
# from 6.4GB to 4.7GB and its reload time from 4.1s to 0.8s (5x), which matters
# because keep_alive's default 5-minute idle timeout means a multi-stage
# pipeline (script, storyboard, topic generation, web grounding) pays that
# reload tax repeatedly whenever stages are spaced further apart than that by
# image/TTS/render work. keep_alive is extended here to outlast a full render.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

TEMP_DIR = "temp"
TEMP_FILE_MAX_AGE_HOURS = 48


def _temp_paths_still_in_use() -> Optional[set]:
    """Every temp/ file path referenced by a generation still in 'draft' or
    'rendering' status -- these must survive cleanup no matter how old, since
    a paused local generation (or one a user is still editing scene-by-scene)
    can legitimately sit for a while. Returns None if the DB can't be read,
    so the caller skips cleanup entirely rather than risk deleting something
    still in use."""
    referenced = set()
    try:
        for gen in db_manager.list_video_generations():
            if gen.get("status") not in ("draft", "drafting", "rendering"):
                continue
            for scene in (gen.get("storyboard") or []):
                for key in ("image_path", "audio_path", "clip_path"):
                    p = scene.get(key)
                    if p:
                        referenced.add(os.path.abspath(p))
    except Exception as e:
        print(f"Temp cleanup: could not read in-progress generations ({e}); skipping this run to be safe.")
        return None
    return referenced


def cleanup_stale_temp_files(max_age_hours: float = TEMP_FILE_MAX_AGE_HOURS) -> int:
    """Delete temp/ files older than max_age_hours, except ones a draft or
    in-progress render still references. Orphaned video_list/audio_list/
    merged_*/scene_*/voice_raw_* files from failed or abandoned runs
    otherwise accumulate in temp/ forever. Runs on startup and after each
    successful render."""
    if not os.path.isdir(TEMP_DIR):
        return 0
    referenced = _temp_paths_still_in_use()
    if referenced is None:
        return 0

    cutoff = time.time() - max_age_hours * 3600
    deleted = 0
    for name in os.listdir(TEMP_DIR):
        path = os.path.abspath(os.path.join(TEMP_DIR, name))
        if path in referenced or not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
        except OSError as e:
            print(f"Temp cleanup: could not remove {path}: {e}")
    if deleted:
        print(f"Temp cleanup: removed {deleted} stale file(s) older than {max_age_hours:.0f}h from {TEMP_DIR}/.")
    return deleted


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        cleanup_stale_temp_files()
    except Exception as e:
        print(f"Startup temp cleanup failed (non-fatal): {e}")
    yield


app = FastAPI(title="AI Video Presenter Backend", version="1.0.0", lifespan=lifespan)

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

# The two entries marked NEW fill formulas that 2026 short-form research names
# as the highest and second-highest performing hook types, not covered by the
# original five (which cluster around one "did you know / secrets" register).
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
        vq.run_ffmpeg(ffmpeg_cmd, label="transition SFX mix")
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
                           duration_preset: str = DEFAULT_DURATION_PRESET, log_callback=None):
    _log = log_callback or print
    hook_instruction = VIRAL_HOOKS.get(hook_style, "")

    # 1. Handle dynamic web search fact checking
    grounding_info = ""
    if enable_search:
        _log("Searching the web for facts to ground the script...")
        try:
            grounding_data = get_web_grounding_context(prompt, model)
            if grounding_data.get("requires_search") and grounding_data.get("context"):
                grounding_info = f"\nVERIFIED INTERNET SEARCH FACTS:\n{grounding_data['context']}\n"
                _log(f"RAG Grounding: Query used: '{grounding_data['search_query']}'. Injected search context successfully.")
        except Exception as e:
            _log(f"Failed to perform web search grounding: {e}")
            
    min_words, max_words, seconds_label = DURATION_PRESETS.get(
        duration_preset, DURATION_PRESETS[DEFAULT_DURATION_PRESET])

    # Stage 1: Creative Story / Script Writer (Free-form text)
    # Smaller local models satisfice on a short, well-formed hook/escalate/
    # payoff/CTA arc and stop, ignoring an abstract total-word target stated
    # only once. Measured live: qwen2.5:7b-instruct returned 23-55 words
    # against a 110-145 word target on 9 straight attempts (3 outer retries x
    # 3 internal retries), never once landing in range. Giving it a concrete
    # SENTENCE COUNT (models track "have I written N sentences yet" far more
    # reliably than "have I written N words yet") and restating the
    # requirement at both the top and bottom of the prompt is the fix.
    # Smaller local models undershoot a stated RANGE, not just an abstract
    # total: measured live even after adding a sentence-count target below,
    # qwen2.5:7b-instruct landed at 67, 104, and 78 words against 110-145 --
    # three straight misses, all under, none over. A range reads as "anywhere
    # in here is fine" and the model anchors low; asking for the ceiling with
    # the floor framed as a hard minimum (not a midpoint to aim near) shifts
    # the whole distribution up instead of retrying the same coin flip.
    target_sentences = max(6, round(max_words / 9))
    min_sentences = max(4, round(min_words / 9))
    storyteller_system = (
        "You are a world-class short-form video scriptwriter for YouTube Shorts, Instagram Reels "
        f"and TikTok whose videos routinely go viral. Write a punchy ~{seconds_label}-second voiceover "
        "script about the given topic.\n"
        f"HARD LENGTH REQUIREMENT: write {target_sentences} sentences, aiming for {max_words} words. "
        f"{min_words} words is the ABSOLUTE FLOOR, not a target -- landing near it is a FAILURE. "
        "A short, complete-sounding script that ends early is a FAILURE even if it has a hook, escalation, "
        "and payoff -- if you're tempted to stop before hitting the sentence count, add another specific "
        "fact, angle, or twist first. Undershooting is a failure; overshooting slightly is fine.\n"
        "VIRAL RULES (follow all):\n"
        "- HOOK FIRST: The opening sentence is the single highest-leverage line in the whole script -- "
        "most viewers decide to keep watching or swipe away within the first 1-3 seconds. It must be "
        "EXACTLY 8-14 words (a viewer reads/hears this in under 3 seconds; longer and you've already "
        "lost the swipe decision). Use a bold contrarian claim, a specific common mistake, a shocking "
        "fact, or a curiosity gap. Never open with 'In this video', 'Today', or a slow intro.\n"
        "- OPEN LOOP: Tease something the viewer only fully understands at the end, so they keep watching.\n"
        "- PACING: Short, punchy, spoken-style sentences (each about 6-12 words) that read cleanly as "
        "on-screen captions. One idea per sentence.\n"
        "- ESCALATE: Each sentence should raise curiosity, tension, or stakes more than the last. Cover "
        f"MULTIPLE distinct facts or angles about the topic (aim for {target_sentences} of them, not fewer) "
        "-- this is what fills the required length without padding or repetition.\n"
        "- PAYOFF + CTA: Land a satisfying payoff, then end with a punchy call to action that tells the "
        "viewer to SUBSCRIBE for more (e.g. 'Subscribe so you never miss one').\n"
        "- Be specific and accurate about the topic; no vague filler or repetition.\n"
        "- Do NOT repeat any sentence or phrase; every line must add new information.\n"
        f"Before you finish, count your sentences. If you have fewer than {target_sentences}, keep going -- "
        f"do not stop at {min_sentences}.\n"
        f"HARD LENGTH REQUIREMENT (again): write {target_sentences} sentences, aiming for {max_words} words. "
        f"{min_words} words is the absolute floor. Output ONLY the raw narration text - no scene numbers, "
        "brackets, speaker names, emojis, or stage directions."
    )
    
    storyteller_prompt = (
        f"System: {storyteller_system}\n{grounding_info}\n"
        f"User: Write a {seconds_label}-second viral story about: {prompt}."
    )
    if hook_instruction:
        storyteller_prompt += f" Hook Instruction: {hook_instruction}"
        
    # This floor used to be a flat 30 words regardless of duration preset --
    # left over from before DURATION_PRESETS existed, when every video targeted
    # ~15-20s (~55-80 words). "Standard" now targets 110-145 words, so a
    # 30-word story passed this check, burned a full storyboard generation, and
    # only then got rejected by validate_script's real min_words floor -- a
    # wasted retry cycle every time, observed live with qwen2.5:7b-instruct.
    # Scaling with min_words catches it here instead, one stage earlier.
    story_word_floor = max(30, int(min_words * 0.7))

    def _extend_story(text: str, words_needed: int) -> str:
        # Hitting an exact word count cold is hard for a small model; continuing
        # existing text by a specific amount is a much easier, more reliable
        # task -- measured live, qwen2.5:7b-instruct oscillated between ~45 and
        # ~103 words against a 110 floor even with an explicit sentence-count
        # target baked into the main prompt, never reliably crossing it from
        # scratch. This is the "add more" pass instead of another cold retry.
        extra_sentences = max(2, round(words_needed / 9))
        extend_prompt = (
            "System: You are extending a short-form video voiceover script that came in too short. "
            f"Add {extra_sentences} more sentences (short, punchy, spoken-style, 6-12 words each) that "
            "introduce NEW specific facts or angles about the topic -- never repeat anything already said. "
            "Insert them before the final subscribe call-to-action line so the payoff still lands last. "
            "Return the COMPLETE script (the original text plus your additions merged in, in order), not "
            "just the new part. Output ONLY the raw narration text - no labels, headers, or explanation.\n"
            f"User: Topic: {prompt}\nCurrent script:\n{text}"
        )
        return llm_client.generate(model, extend_prompt, timeout=90).strip()

    def _attempt_story():
        # Generous timeout for cloud models; they are slow but usually succeed on retry.
        t = llm_client.generate(model, storyteller_prompt, timeout=150)
        wc = len(t.split())
        if wc < story_word_floor:
            raise RuntimeError(f"story too short ({wc} words; need >= {story_word_floor})")
        if wc < min_words:
            try:
                extended = _extend_story(t, min_words - wc)
                if len(extended.split()) > wc:
                    t = extended
            except Exception as e:
                print(f"Story extension failed ({e}); using original {wc}-word story.")
        return t

    _log(f"Generating story (up to 3 attempts) with {model}...")
    try:
        story_text = retry_call(_attempt_story, attempts=3, base_delay=2.0,
                                label="story text", logger=_log)
        _log("Story generated.")
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
        "1. 'narration': a LITERAL split of the story's own sentences into 7 groups, in order -- copy the "
        "story's exact wording, do not summarize, paraphrase, shorten, or compress it. The 7 narration "
        "fields, concatenated in order, must reproduce the ENTIRE story text with nothing lost and no words "
        f"dropped: if the story is {min_words}+ words, your 7 narration fields combined must also total "
        f"{min_words}+ words. Do not invent new facts, and do not omit any sentence from the story.\n"
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

    # Stage 2 is the flaky step (cloud models time out / return slightly-off JSON).
    # Retry it, accept a reasonable scene count, and normalize to exactly 7.
    def _attempt_storyboard():
        # Measured live: OpenRouter's z-ai/glm-5.3-flash took 253s for this
        # exact 7-scene JSON storyboard call -- a 120s timeout guaranteed
        # failure on every attempt (and, before the hard-deadline fix in
        # llm_client.generate, hung indefinitely past that instead of raising).
        # 280s gives a real chance to succeed rather than always falling back.
        text = llm_client.generate(model, storyboarder_prompt, timeout=280, json_mode=True)
        data = json.loads(clean_json_response(text))
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or len(scenes) < 4:
            raise RuntimeError(f"invalid storyboard (got {len(scenes) if isinstance(scenes, list) else 'no'} scenes)")
        return data

    _log("Segmenting story into a 7-scene storyboard...")
    try:
        data = retry_call(_attempt_storyboard, attempts=2, base_delay=2.0,
                          label="storyboard JSON", logger=_log)
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
                              enable_search=False, attempts=3, log=print,
                              art_style="Photorealistic",
                              duration_preset=DEFAULT_DURATION_PRESET,
                              max_seconds=360.0):
    """Generate a script and run it through the deterministic viral checker.

    Regenerates on HARD failures (off-topic, repeats, wrong length, fallback,
    a hook that runs long...), auto-fixes SOFT issues (missing CTA, non-realistic
    style), and raises if it still cannot produce a valid script - so a broken
    video never reaches render.

    Two things keep a bad first attempt from costing a full second LLM round
    trip: ``mechanically_fix_hard_issues`` corrects an over-length hook or a
    duplicated CTA line in place (the only two hard issues that don't need the
    LLM's judgment to fix), and ``max_seconds`` caps the total wall-clock spend
    -- 3 attempts x a multi-stage local-7B generation can exceed 6 minutes, so
    once the deadline passes this returns the least-bad attempt seen so far
    (autofixed, with its remaining issues attached as a warning) instead of
    leaving the caller waiting through a full 3rd attempt for a result that
    then still gets thrown away.
    """
    min_words, max_words, _label = DURATION_PRESETS.get(
        duration_preset, DURATION_PRESETS[DEFAULT_DURATION_PRESET])
    last_hard = ["unknown error"]
    best_data, best_hard = None, None
    start = time.time()

    for attempt in range(1, attempts + 1):
        if attempt > 1 and time.time() - start > max_seconds:
            log(f"[validator] {time.time() - start:.0f}s elapsed, over the {max_seconds:.0f}s "
                f"budget; stopping after attempt {attempt - 1} instead of trying again.")
            break

        log(f"Drafting script (attempt {attempt}/{attempts})...")
        try:
            data = generate_ollama_script(prompt, model, hook_style, enable_search=enable_search,
                                          art_style=art_style, duration_preset=duration_preset,
                                          log_callback=log)
        except Exception as e:
            last_hard = [f"generation error: {e}"]
            log(f"[validator] attempt {attempt}/{attempts}: {last_hard[0]}")
            continue

        hard, soft = validate_script(data, prompt, art_style=art_style,
                                     min_words=min_words, max_words=max_words)
        if hard:
            data, hard = mechanically_fix_hard_issues(data, hard, min_words=min_words)
            if hard:
                log(f"[validator] mechanical fixes left {len(hard)} issue(s) unresolved: {hard}")
            else:
                log("[validator] fixed hard issues in place (hook trim / CTA dedupe) -- no regeneration needed.")

        if not hard:
            if soft:
                log(f"[validator] auto-fixing soft issues: {soft}")
            return autofix(data, art_style=art_style)  # enforce style + ensure CTA

        if best_hard is None or len(hard) < len(best_hard):
            best_data, best_hard = data, hard
        last_hard = hard
        log(f"[validator] attempt {attempt}/{attempts} rejected (regenerating): {hard}")

    if best_data is not None:
        log(f"[validator] returning the least-bad attempt with unresolved issues: {best_hard}")
        best_data["_validation_warnings"] = best_hard
        return autofix(best_data, art_style=art_style)

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
        vq.run_ffmpeg(ffmpeg_cmd, label="silence trim")
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
            vq.run_ffmpeg(ffmpeg_cmd, label="kid-pitch voice effect")
            try:
                os.remove(raw_output_path)
            except Exception:
                pass
            audio_path = pitch_output_path
            
        elif effect == "Deep (Low Pitch)":
            pitch_output_path = os.path.abspath(os.path.join("temp", f"voice_deep_{int(time.time())}.wav"))
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", raw_output_path, "-af", "asetrate=24000*0.82,atempo=1/0.82", pitch_output_path]
            vq.run_ffmpeg(ffmpeg_cmd, label="deep-pitch voice effect")
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
    # OpenRouter models only show up once a key is configured -- picking one
    # from this same dropdown is the only opt-in `llm_client` needs, since it
    # routes by the "/" in the model id rather than a separate provider field.
    if llm_client.OPENROUTER_API_KEY:
        for m in llm_client.OPENROUTER_MODELS:
            if m not in models:
                models.append(m)
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
        # Local Ollama stays the default even when an OpenRouter key is
        # configured: measured live, OpenRouter's z-ai/glm-5.3-flash took 253s
        # for the storyboard JSON stage alone (vs. ~50-65s total for the local
        # model) -- correct and eventually-successful, but far slower than the
        # thing OpenRouter was added to fix. It's still one dropdown pick away
        # for when local Ollama is unavailable or its cloud quota is exhausted.
        "default_model": (ollama_models[0] if ollama_models else ""),
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


def concat_with_fallback(list_path: str, output_path: str, label: str) -> None:
    """Stream-copy concat is the fast path; fall back to a re-encoding concat
    when it fails. Stock Pexels clips, Hailuo motion clips, and Ken Burns
    slideshow segments are each produced by a different code path, and despite
    sharing vq.intermediate_encode_args() can still end up differing enough
    (container-level details -c copy is sensitive to) that -c copy concat
    rejects them -- surfaced live as ffmpeg exit 183 with the real reason
    thrown away by the old stderr=DEVNULL call."""
    try:
        vq.run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
             "-c", "copy", output_path],
            label=f"{label} concat (stream copy)",
        )
    except RuntimeError as e:
        print(f"{label} concat via stream copy failed ({e}); re-encoding instead.")
        is_audio = output_path.lower().endswith(".wav")
        reencode_args = (["-c:a", "pcm_s16le"] if is_audio else
                         ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(vq.FPS)])
        vq.run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
            + reencode_args + [output_path],
            label=f"{label} concat (re-encode fallback)",
        )


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
    
    # A concat list built from an empty or partially-missing scene set fails at
    # ffmpeg with an opaque, unhelpful exit code (183) and no indication the
    # real problem was upstream (e.g. an empty storyboard reaching the
    # renderer). Fail loudly here instead, naming exactly what's missing.
    if not scene_videos or not scene_audios:
        raise RuntimeError(
            f"No scene segments to render: got {len(scene_videos)} video and "
            f"{len(scene_audios)} audio segment(s) for {len(scenes)} scene(s) "
            "in the storyboard. The storyboard sent to the renderer is empty "
            "or scene processing produced nothing -- check the caller."
        )
    missing_video = [p for p in scene_videos if not os.path.exists(p)]
    missing_audio = [p for p in scene_audios if not os.path.exists(p)]
    if missing_video or missing_audio:
        raise RuntimeError(
            "Scene segment file(s) went missing before concat -- "
            f"video: {missing_video or 'none missing'}, audio: {missing_audio or 'none missing'}"
        )

    video_list_path = os.path.abspath(os.path.join("temp", f"video_list_{timestamp}.txt"))
    audio_list_path = os.path.abspath(os.path.join("temp", f"audio_list_{timestamp}.txt"))

    with open(video_list_path, "w") as vf:
        for p in scene_videos:
            vf.write(f"file '{p}'\n")
    with open(audio_list_path, "w") as af:
        for p in scene_audios:
            af.write(f"file '{p}'\n")

    concat_with_fallback(video_list_path, merged_video, "video")
    concat_with_fallback(audio_list_path, merged_audio, "audio")

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

def run_draft_task(gen_id: str, req: "DraftRequest") -> None:
    """Background counterpart of api_draft_script.

    A synchronous /api/draft-script held one HTTP request open for the whole
    script+storyboard generation -- reproduced live: a request with a local
    7B model and web search enabled produced no response in 280s (the client
    gave up; the endpoint had no way to report progress or an intermediate
    timeout). Running this as a background job lets the client return
    immediately with a generation_id and poll /api/generation-status for
    progress, matching the pattern already used for rendering.
    """
    logs: list = []

    def _log(msg: str) -> None:
        logs.append(msg)
        print(msg)
        db_manager.update_video_generation(gen_id, logs=logs)

    try:
        script_data = generate_validated_script(req.prompt, req.model, req.hook_style,
                                                 enable_search=req.enable_search, art_style=req.art_style,
                                                 duration_preset=req.duration_preset, log=_log)
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

        if script_data.get("_validation_warnings"):
            _log(f"Draft ready with unresolved issues (used the least-bad attempt): "
                 f"{script_data['_validation_warnings']}")

        db_manager.update_video_generation(
            gen_id, topic=script_data.get("topic", req.prompt),
            script_data=script_data, storyboard=storyboard, status="draft",
        )
    except Exception as e:
        _log(f"Draft failed: {e}")
        db_manager.update_video_generation(gen_id, status="failed", error_message=str(e))
        notify("Draft script failed", f"Draft for '{req.prompt}' failed: {e}",
              context={"generation_id": gen_id})


@app.post("/api/draft-script")
def api_draft_script(req: DraftRequest, background_tasks: BackgroundTasks):
    gen_id = str(uuid.uuid4())
    db_manager.create_video_generation(
        gen_id, req.prompt, req.prompt, None, None, status="drafting"
    )
    background_tasks.add_task(run_draft_task, gen_id, req)
    return {"success": True, "generation_id": gen_id, "status": "drafting"}

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
        try:
            cleanup_stale_temp_files()
        except Exception as e:
            print(f"Post-render temp cleanup failed (non-fatal): {e}")
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
    """Upload to YouTube now. Always immediate: the deferred/scheduled-time
    path and its background polling thread were removed along with the rest
    of the autonomous scheduler -- this is a one-click publish button."""
    job_id = str(uuid.uuid4())

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
        {},
        status="running",
    )

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
    script_data = gen.get("script_data") or {}
    return {
        "status": gen["status"],
        # Progress stages while status == 'drafting' or 'rendering' (e.g.
        # "generating story (attempt 2/3)"), so the frontend can poll this
        # instead of holding one HTTP request open for a multi-minute
        # local-LLM script generation.
        "logs": gen.get("logs") or [],
        "error_message": gen.get("error_message"),
        "topic": gen.get("topic"),
        "video_url": static_url(video_path),
        "thumbnail_url": thumbnail_url_for(video_path),
        "storyboard": gen["storyboard"],
        "youtube_metadata": script_data.get("youtube_metadata"),
        "instagram_metadata": script_data.get("instagram_metadata"),
        "validation_warnings": script_data.get("_validation_warnings"),
    }

@app.delete("/api/generation/{generation_id}")
def api_delete_generation(generation_id: str):
    try:
        db_manager.delete_video_generation(generation_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/upload-status/{job_id}")
def get_upload_status(job_id: str):
    job = db_manager.get_upload_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    return job


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
