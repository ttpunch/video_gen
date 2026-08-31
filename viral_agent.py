#!/usr/bin/env python3
import os
import sys
import time
import json
import uuid
import re
import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add current folder to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

import db_manager
from backend import run_viral_shorts_pipeline_new, generate_validated_script
from search_helper import get_web_grounding_context, clean_json_response
from uploader_youtube import upload_video_to_youtube, is_youtube_authenticated
from notifier import notify
from curiosity_topics import select_curiosity_topic

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

CONFIG_FILE = os.path.abspath("scheduler_config.json")
LOGS_FILE = os.path.abspath("scheduler_logs.json")

# --- Revenue (RPM) reference data --------------------------------------------
# RPM (revenue per mille / per 1000 monetized views) varies hugely by viewer
# geography and by content niche. These are curated approximate USD ranges used
# only to GUIDE topic choice toward higher-earning markets/niches — they are not
# exact earnings. Live per-niche RPM is not available via any public API.
RPM_BY_GEO = {
    "US": (4.0, 14.0),   # Highest RPM market
    "AU": (3.0, 10.0),
    "CA": (2.8, 9.0),
    "GB": (2.5, 8.5),
    "_default": (0.3, 2.0),
}

# Multiplier applied on top of the geo range, by broad niche.
RPM_BY_NICHE = {
    "finance": 2.2, "investing": 2.2, "business": 1.9, "money": 2.0,
    "tech": 1.7, "ai": 1.7, "software": 1.7, "crypto": 1.8,
    "science": 1.2, "education": 1.2, "psychology": 1.2,
    "entertainment": 0.8, "sports": 0.9, "culture": 0.9, "general": 1.0,
}

# High-CPM markets the recommender is allowed to target.
ALLOWED_RPM_GEOS = ["US", "GB", "CA", "AU"]


def estimate_rpm(geo, niche):
    """Return a human-readable estimated RPM range string like '$6–$21' for a
    given viewer geography and content niche."""
    low, high = RPM_BY_GEO.get((geo or "US").upper(), RPM_BY_GEO["_default"])
    mult = RPM_BY_NICHE.get((niche or "general").strip().lower(), 1.0)
    return f"${low * mult:.0f}–${high * mult:.0f}"

def load_scheduler_config():
    """Load configuration from scheduler_config.json or create defaults."""
    default_config = {
        "enabled": False,
        "region": "US",
        "time1": "10:00",
        "time2": "18:00",
        "model": "deepseek-v4-pro:cloud",
        "leonardo_model": "Leonardo Phoenix 1.0 (General/Realistic)",
        "voice": "Sarah (Female - US - Soft)",
        "privacy": "private",
        "require_approval": False,
        "image_provider": "local",
        "videos_per_run": 1,
        # Topic source: "trends" (live Google Trends), "curiosity" (curated
        # evergreen library), or "mixed" (randomly alternate between the two).
        "topic_source": "trends",
        "curiosity_category": "All",
        "subscribe_overlay": True,
        "channel_handle": "",
        "youtube_channel_url": "",
        "last_run_date": "",
        "last_run_slots": []
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                # Ensure all default keys exist
                for k, v in default_config.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception as e:
            print(f"Error loading scheduler config: {e}")
    return default_config

def save_scheduler_config(config):
    """Save configuration to scheduler_config.json."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving scheduler config: {e}")

def load_scheduler_logs():
    """Load scheduler execution logs."""
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_scheduler_logs(logs):
    """Save scheduler logs to scheduler_logs.json."""
    try:
        with open(LOGS_FILE, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Error saving scheduler logs: {e}")

def fetch_google_trends(geo="US"):
    """Fetch top Google Trends RSS for the specified country geo code."""
    url = f"https://trends.google.com/trending/rss?geo={geo.upper()}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch trends: HTTP {response.status_code}")
            return []
        
        root = ET.fromstring(response.text)
        namespaces = {'ht': 'https://trends.google.com/trending/rss'}
        
        items = []
        for item in root.findall('.//item'):
            title = item.find('title').text
            traffic_el = item.find('ht:approx_traffic', namespaces)
            traffic = traffic_el.text if traffic_el is not None else "Unknown"
            
            news_items = []
            for news in item.findall('ht:news_item', namespaces):
                news_title = news.find('ht:news_item_title', namespaces)
                news_snippet = news.find('ht:news_item_snippet', namespaces)
                news_title_text = news_title.text if news_title is not None else ""
                news_snippet_text = news_snippet.text if news_snippet is not None else ""
                news_items.append(f"{news_title_text}: {news_snippet_text}")
                
            summary = " | ".join(news_items[:2])
            items.append({
                "title": title,
                "traffic": traffic,
                "summary": summary
            })
        return items
    except Exception as e:
        print(f"Error fetching Google Trends RSS: {e}")
        return []

def select_viral_topic(trends_list, ollama_model, performance_hint="", exclude_topics=None):
    """Use Ollama LLM to select a safe, educational, high-engagement topic from the trends list.

    ``performance_hint`` (from the analytics feedback loop) is appended to the
    prompt so the model can favor themes that performed well historically.
    ``exclude_topics`` is a list of recently-used topics to avoid (prevents the
    scheduler from making the same video repeatedly).
    """
    if not trends_list:
        return None, "No trends available."
        
    url = f"http://localhost:11434/api/generate"
    
    # Strictly enforce safety filtering in LLM instructions to avoid strikes/violations
    system_prompt = (
        "You are an elite viral content strategist for YouTube Shorts, Instagram Reels and TikTok. "
        "From the provided Google Trends list, choose the SINGLE topic with the highest viral potential "
        "for a 15-second vertical video.\n\n"
        "CHOOSE THE TOPIC WITH THE STRONGEST:\n"
        "- Curiosity gap or surprise (the 'wait, what?!' factor)\n"
        "- Emotional pull (awe, shock, inspiration, nostalgia, or satisfying payoff)\n"
        "- Broad relatability and 'did you know' shareability\n"
        "- A clear, punchy story that genuinely fits in 15 seconds\n\n"
        "STRICT SAFETY FILTERING (reject and skip):\n"
        "1. Violence, accidents, death, disasters, crime, war, political controversy, scandals, or adult themes.\n"
        "2. Medical or health advice/claims (avoids misinformation strikes).\n"
        "3. Prefer angles in science, space, history, technology, nature, psychology, or sports/culture "
        "with an educational or human-interest hook.\n\n"
        "Then rewrite the chosen trend as a SHORT, curiosity-driven video title (hook-style, not a plain news headline).\n"
        "Respond ONLY with a valid JSON object, with no markdown code fences, no conversational filler, and no extra text:\n"
        "{\n"
        "  \"topic\": \"A short, curiosity-driven video title based on the chosen trend\",\n"
        "  \"rationale\": \"One sentence on why this is safe AND has high viral potential\"\n"
        "}"
    )
    
    trends_text = ""
    for idx, item in enumerate(trends_list[:12]):
        trends_text += f"{idx+1}. Topic: {item['title']}, Traffic: {item['traffic']}, News: {item['summary']}\n"
        
    if performance_hint:
        system_prompt += "\n\n" + performance_hint

    if exclude_topics:
        avoid = "; ".join(str(t) for t in exclude_topics[:25])
        system_prompt += (
            "\n\nDO NOT pick any topic that is the same as or similar to these already-used topics "
            f"(choose a clearly DIFFERENT subject): {avoid}"
        )

    full_prompt = f"System: {system_prompt}\nTrends List:\n{trends_text}"
    
    payload = {
        "model": ollama_model,
        "prompt": full_prompt,
        "stream": False,
        "format": "json",
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_ctx": OLLAMA_NUM_CTX}
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            resp_text = response.json().get("response", "").strip()
            # Clean JSON fences if any
            if resp_text.startswith("```"):
                lines = resp_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                resp_text = "\n".join(lines).strip()
                
            data = json.loads(resp_text)
            topic = data.get("topic")
            rationale = data.get("rationale", "")
            return topic, rationale
    except Exception as e:
        print(f"Ollama topic selection failed: {e}")
        
    # Fallback to a safe random trend if LLM fails
    for trend in trends_list:
        # Simple local word-filter safety check
        lower_title = trend["title"].lower()
        unsafe_words = ["kill", "die", "dead", "shoot", "murder", "accident", "crash", "war", "scandal", "arrest", "polic", "assault"]
        if not any(w in lower_title for w in unsafe_words):
            return trend["title"], "Fallback safe selection."
            
    return None, "No safe trends found."

def recommend_viral_topics(trends_list, ollama_model, count=5, performance_hint="",
                           exclude_topics=None, high_cpm_bias=True, geo="US"):
    """Rank the trends into the top ``count`` ready-to-use viral video topics,
    optimized for revenue (RPM).

    Returns a list of dicts: {title, rationale, niche, rpm_tier, est_rpm, geo}.
    Generalizes ``select_viral_topic`` (which returns a single pick) — that
    function is left intact for the scheduler.
    """
    geo = (geo or "US").upper()
    if not trends_list:
        return []

    revenue_directive = ""
    if high_cpm_bias:
        revenue_directive = (
            "\nREVENUE OPTIMIZATION (important):\n"
            "These videos must EARN. Strongly prefer topics in high-CPM niches that pay "
            "advertisers the most: personal finance, investing, money/side-hustles, business, "
            "technology, AI, software, and crypto. A genuinely viral high-CPM angle beats a "
            "viral low-CPM entertainment angle. Still REQUIRE real viral pull — never pick a "
            "boring topic just because the niche pays well.\n"
            "Classify each pick's niche as one of: finance, investing, business, money, tech, "
            "ai, software, crypto, science, education, psychology, sports, culture, "
            "entertainment, general.\n"
        )

    system_prompt = (
        "You are an elite viral content strategist for YouTube Shorts. "
        f"The audience is in {geo} (a high-RPM market). From the provided Google Trends list, "
        f"choose the TOP {count} topics with the highest viral potential for 15-second vertical videos.\n\n"
        "RANK BY:\n"
        "- Curiosity gap or surprise (the 'wait, what?!' factor)\n"
        "- Emotional pull (awe, shock, inspiration, satisfying payoff)\n"
        "- Broad relatability and 'did you know' shareability\n"
        "- A clear, punchy story that genuinely fits in 15 seconds\n"
        + revenue_directive +
        "\nSTRICT SAFETY FILTERING (reject and skip):\n"
        "1. Violence, accidents, death, disasters, crime, war, political controversy, scandals, or adult themes.\n"
        "2. Medical or health advice/claims.\n\n"
        "Rewrite each chosen trend as a SHORT, curiosity-driven video title (hook-style, not a plain news headline).\n"
        "Assign each a rpm_tier of \"High\", \"Medium\", or \"Low\" reflecting how much that niche typically earns.\n"
        "Respond ONLY with a valid JSON object, no markdown fences, no extra text:\n"
        "{\n"
        "  \"topics\": [\n"
        "    {\"title\": \"short curiosity-driven title\", \"rationale\": \"one sentence: why it is safe AND viral AND earns\", \"niche\": \"finance|tech|science|...\", \"rpm_tier\": \"High|Medium|Low\"}\n"
        "  ]\n"
        "}"
    )

    trends_text = ""
    for idx, item in enumerate(trends_list[:12]):
        trends_text += f"{idx+1}. Topic: {item['title']}, Traffic: {item['traffic']}, News: {item['summary']}\n"

    if performance_hint:
        system_prompt += "\n\n" + performance_hint

    if exclude_topics:
        avoid = "; ".join(str(t) for t in exclude_topics[:25])
        system_prompt += (
            "\n\nDO NOT pick any topic that is the same as or similar to these already-used topics "
            f"(choose clearly DIFFERENT subjects): {avoid}"
        )

    full_prompt = f"System: {system_prompt}\nTrends List:\n{trends_text}"
    payload = {"model": ollama_model, "prompt": full_prompt, "stream": False, "format": "json",
              "keep_alive": OLLAMA_KEEP_ALIVE, "options": {"num_ctx": OLLAMA_NUM_CTX}}

    recs = []
    try:
        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60)
        if response.status_code == 200:
            resp_text = clean_json_response(response.json().get("response", "").strip())
            data = json.loads(resp_text)
            for t in data.get("topics", [])[:count]:
                title = (t.get("title") or "").strip()
                if not title:
                    continue
                niche = (t.get("niche") or "general").strip().lower()
                recs.append({
                    "title": title,
                    "rationale": t.get("rationale", ""),
                    "niche": niche,
                    "rpm_tier": t.get("rpm_tier", "Medium"),
                    "est_rpm": estimate_rpm(geo, niche),
                    "geo": geo,
                })
    except Exception as e:
        print(f"Ollama topic recommendation failed: {e}")

    if recs:
        return recs

    # Fallback: safety-filtered raw trends so the UI still populates if the LLM is down.
    unsafe_words = ["kill", "die", "dead", "shoot", "murder", "accident", "crash",
                    "war", "scandal", "arrest", "polic", "assault"]
    for trend in trends_list:
        if any(w in trend["title"].lower() for w in unsafe_words):
            continue
        recs.append({
            "title": trend["title"],
            "rationale": "Trending now (AI ranking unavailable — raw trend).",
            "niche": "general",
            "rpm_tier": "Medium",
            "est_rpm": estimate_rpm(geo, "general"),
            "geo": geo,
        })
        if len(recs) >= count:
            break
    return recs

def _run_single_video(topic, rationale, slot_name, config, ollama_model, all_logs,
                      context="", hook_style="Did You Know? (Fact Hook)",
                      duration_preset=None):
    """Generate, render and publish ONE video for the given topic.

    ``context`` is an optional curiosity angle/hook that is woven into the
    script-drafting prompt so the video leans into the intended angle (used by
    the curiosity topic source). ``topic`` stays clean for logs, the DB record
    and the eventual YouTube title.

    Appends its own log entry to ``all_logs`` and returns it.
    """
    job_id = str(uuid.uuid4())
    execution_logs = []

    def log_step(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        print(entry)
        execution_logs.append(entry)

    log_entry = {
        "id": job_id,
        "timestamp": datetime.now().isoformat() + "Z",
        "slot": slot_name,
        "topic": topic,
        "status": "running",
        "video_path": None,
        "youtube_id": None,
        "logs": execution_logs
    }
    all_logs.insert(0, log_entry)
    save_scheduler_logs(all_logs)

    try:
        log_step(f"Selected Topic: '{topic}'")
        log_step(f"Rationale: {rationale}")
        save_scheduler_logs(all_logs)

        # 3. Web search grounding
        log_step("Performing real-time Web Search Grounding for factual verification...")
        grounding_data = get_web_grounding_context(topic, ollama_model)
        web_context = grounding_data.get("context", "")
        if web_context:
            log_step(f"Factual grounding context retrieved successfully (query: '{grounding_data.get('search_query')}').")
        else:
            log_step("No web grounding context retrieved. Proceeding with LLM knowledge base.")
            
        # 4. Draft script & storyboard (validated against the viral checklist + photorealism)
        log_step("Drafting script and segmenting storyboard scenes...")
        script_prompt = topic
        if context:
            log_step(f"Applying curiosity angle as script context: {context}")
            script_prompt = f"{topic}. Curiosity angle to emphasize: {context}"
        from backend import DEFAULT_DURATION_PRESET
        script_data = generate_validated_script(
            script_prompt, ollama_model, hook_style=hook_style,
            enable_search=bool(web_context), log=log_step,
            duration_preset=duration_preset or DEFAULT_DURATION_PRESET,
        )
        scenes = script_data.get("scenes")
        if not scenes or len(scenes) != 7:
            raise Exception("Failed to generate a valid 7-scene script and storyboard.")
            
        # Overwrite all scene speaker voices with the chosen scheduler voice
        selected_voice = config.get("voice", "Sarah (Female - US - Soft)")
        log_step(f"Overriding all storyboard scene speaker voices to selected voice: {selected_voice}")
        for idx, scene in enumerate(scenes):
            scene["speaker"] = selected_voice
            
        log_step("Cohesive story script and 7 storyboard scenes drafted successfully.")
        
        # 5. Initialize DB video generation record
        gen_id = str(uuid.uuid4())
        db_manager.create_video_generation(
            gen_id, topic, topic, script_data, scenes, status="rendering"
        )
        log_step(f"Registered video generation record in database. Gen ID: {gen_id}")
        
        # 6. Render video with 100% Procedural Real-time Ambient Music
        log_step("Rendering final video. Visual mode: Cinematic Slideshow, Music: Procedural Ambient...")
        
        final_video, final_storyboard, topic_out, script_data_out = run_viral_shorts_pipeline_new(
            prompt="",
            model="",
            visual_mode="Cinematic Slideshow",
            leonardo_model=config.get("leonardo_model", "Leonardo Phoenix 1.0 (General/Realistic)"),
            voice=config.get("voice", "Sarah (Female - US - Soft)"),
            speed=1.0,
            music_style="Procedural Ambient",  # Force procedural music synthesis!
            satisfying_background="None",
            enable_captions=config.get("enable_captions", True),
            caption_font=config.get("caption_font", "Arial"),
            caption_size=config.get("caption_size", 72),
            caption_margin_v=config.get("caption_margin_v", 150),
            caption_color=config.get("caption_color", "&H00FFFF&"),
            caption_style=config.get("caption_style", "Viral Pop"),
            enable_transition_sfx=False,
            custom_storyboard=scenes,
            custom_script_data=script_data,
            log_callback=log_step,
            on_scene_complete=lambda sb: db_manager.update_video_generation(gen_id, storyboard=sb),
            generation_id=gen_id,
            image_provider=config.get("image_provider", "local"),
            subscribe_overlay=config.get("subscribe_overlay", True),
            channel_handle=config.get("channel_handle", "")
        )
        
        log_step(f"Video rendering completed successfully! Final Path: {final_video}")
        
        # Update db generation status
        db_manager.update_video_generation(
            gen_id, storyboard=final_storyboard, final_video_path=final_video, status="completed"
        )
        
        log_entry["video_path"] = final_video
        save_scheduler_logs(all_logs)
        
        # 7. Approval gate: when enabled, hold for human review instead of auto-publishing.
        if config.get("require_approval"):
            yt_meta = script_data.get("youtube_metadata") or {}
            yt_title = yt_meta.get("title", f"{topic} #shorts #viral")
            if "#shorts" not in yt_title.lower():
                yt_title = f"{yt_title[:80]} #shorts"
            _ch = config.get("youtube_channel_url", "")
            _sub = f"\n\n🔔 SUBSCRIBE for daily videos{': ' + _ch if _ch else '!'}"
            yt_desc = yt_meta.get("description", "Daily educational shorts.") + _sub + "\n\n#shorts #trending #facts"
            yt_tags = yt_meta.get("tags") or ["shorts", "facts", "viral"]
            privacy_status = config.get("privacy", "private")

            approval_job_id = str(uuid.uuid4())
            db_manager.create_upload_job(
                approval_job_id, gen_id, ["youtube"],
                youtube_metadata={"title": yt_title, "description": yt_desc, "tags": yt_tags, "privacy": privacy_status},
                instagram_metadata=None,
                status="pending_approval",
                scheduled_time=datetime.now().isoformat() + "Z"
            )
            db_manager.update_upload_job(approval_job_id, logs=execution_logs)
            log_step(f"Video generated and held for approval (job {approval_job_id}). Approve it in the Publisher panel to publish.")
            notify(
                "Video awaiting approval",
                f"'{topic}' was generated and is awaiting manual approval before publishing.",
                level="info",
                context={"topic": topic, "job_id": approval_job_id, "generation_id": gen_id}
            )
            log_step("Daily Auto-Agent run completed successfully (pending approval)!")
            log_entry["status"] = "success"
            save_scheduler_logs(all_logs)
            return log_entry

        # 7b. Upload to YouTube (if credentials exist)
        log_step("Checking YouTube OAuth authorization...")
        if db_manager.is_platform_uploaded(gen_id, "youtube"):
            prev = db_manager.get_platform_upload(gen_id, "youtube")
            log_step(f"YouTube: this generation was already published (video id {prev['external_id']}); skipping upload.")
            log_entry["youtube_id"] = prev["external_id"]
        elif is_youtube_authenticated():
            log_step("YouTube credentials authenticated. Starting video upload...")

            yt_meta = script_data.get("youtube_metadata") or {}
            yt_title = yt_meta.get("title", f"{topic} #shorts #viral")
            if "#shorts" not in yt_title.lower():
                yt_title = f"{yt_title[:80]} #shorts"
                
            _ch = config.get("youtube_channel_url", "")
            _sub = f"\n\n🔔 SUBSCRIBE for daily videos{': ' + _ch if _ch else '!'}"
            yt_desc = yt_meta.get("description", "Daily educational shorts.") + _sub + "\n\n#shorts #trending #facts"
            yt_tags = yt_meta.get("tags") or ["shorts", "facts", "viral"]
            privacy_status = config.get("privacy", "private")
            
            def upload_progress(pct):
                log_step(f"YouTube Upload Progress: {pct}%")
                
            from backend import video_used_synthetic_media
            yt_video_id = upload_video_to_youtube(
                final_video,
                title=yt_title,
                description=yt_desc,
                tags=yt_tags,
                privacy_status=privacy_status,
                progress_callback=upload_progress,
                contains_synthetic_media=video_used_synthetic_media(scenes),
            )
            
            log_step(f"YouTube Upload Successful! Video ID: {yt_video_id}")
            log_entry["youtube_id"] = yt_video_id

            # Record in dedup ledger so a re-run never double-publishes this generation.
            db_manager.record_platform_upload(gen_id, "youtube", yt_video_id)

            # Record upload job in database for transparency
            upload_job_id = str(uuid.uuid4())
            db_manager.create_upload_job(
                upload_job_id, gen_id, ["youtube"],
                youtube_metadata={"title": yt_title, "description": yt_desc, "tags": yt_tags, "privacy": privacy_status},
                instagram_metadata=None,
                status="completed",
                scheduled_time=datetime.now().isoformat() + "Z"
            )
            db_manager.update_upload_job(upload_job_id, logs=execution_logs)
        else:
            log_step("⚠️ WARNING: YouTube is NOT authenticated. Skipping upload. Please authorize YouTube in the Publisher panel.")
            
        log_step("Auto-Agent video completed successfully!")
        log_entry["status"] = "success"

    except Exception as e:
        log_step(f"❌ ERROR: Auto-Agent video failed: {str(e)}")
        log_entry["status"] = "failed"
        notify(
            "Viral agent video failed",
            f"Autonomous viral agent ({slot_name}) failed for topic '{topic}': {e}",
            context={"slot": slot_name, "topic": topic}
        )

    save_scheduler_logs(all_logs)
    return log_entry


def run_viral_agent_job(slot_name, config=None):
    """Run the autonomous agent, producing ``config['videos_per_run']`` videos,
    each on a DIFFERENT topic (avoiding recently-used and within-run repeats)."""
    if not config:
        config = load_scheduler_config()

    count = max(1, int(config.get("videos_per_run", 1) or 1))
    region = config.get("region", "US")
    ollama_model = config.get("model", "deepseek-v4-pro:cloud")
    topic_source = str(config.get("topic_source", "trends") or "trends").lower()
    curiosity_category = config.get("curiosity_category", "All") or "All"
    # Optional: constrains every generated topic to one interest (e.g.
    # "cricket", "cooking"). 2026 short-form research finds channels that
    # reinforce one topic for ~30 days build audience faster than ones that
    # jump subject every video; leaving this blank keeps the fully open-ended
    # behaviour (any subject the model knows, never repeating) unchanged.
    channel_niche = str(config.get("channel_niche", "") or "").strip()
    all_logs = load_scheduler_logs()

    # The "trends" source used to fetch Google Trends and rank the ~10 raw
    # headlines with ``select_viral_topic``, which silently fell back to
    # unranked, un-safety-filtered raw trend titles whenever the LLM's JSON
    # parse failed -- undetectable from the logs, and the actual cause of
    # unattended uploads like a raw criminal-trial headline reaching a video
    # topic. ``trend_analyser`` generates and hard-filters topics instead of
    # ranking a thin scraped pool, and raises loudly on failure rather than
    # degrading silently. Gathered once per run (not once per video) so a
    # multi-video run does not repeat the Trends/Wikipedia network round trip.
    signals = None
    if topic_source in ("trends", "mixed"):
        import trend_analyser
        print(f"[agent] Run '{slot_name}': generating {count} video(s). Gathering trend signals ({region})...")
        try:
            signals = trend_analyser.gather_signals(region)
        except Exception as e:
            print(f"[agent] Trend signal gathering failed ({e}); "
                 f"{'falling back to curiosity topics' if topic_source == 'mixed' else 'this run will fail'}.")
            if topic_source == "trends":
                ts = datetime.now().strftime("%H:%M:%S")
                entry = {
                    "id": str(uuid.uuid4()), "timestamp": datetime.now().isoformat() + "Z",
                    "slot": slot_name, "topic": "N/A", "status": "failed", "video_path": None,
                    "youtube_id": None,
                    "logs": [f"[{ts}] Trend signal gathering failed: {e}"],
                }
                all_logs.insert(0, entry)
                save_scheduler_logs(all_logs)
                notify("Viral agent run failed", f"Trend signal gathering failed: {e}", context={"slot": slot_name})
                return entry
    else:
        print(f"[agent] Run '{slot_name}': generating {count} video(s) from curated curiosity topics ({curiosity_category}).")

    # Avoid topics already produced recently (across days) and within this run.
    try:
        used_topics = list(db_manager.get_recent_topics(40))
    except Exception:
        used_topics = []

    performance_hint = ""
    try:
        from analytics import get_performance_hint
        performance_hint = get_performance_hint()
    except Exception:
        pass

    # Every unattended video used to open with the identical hardcoded
    # "Did You Know?" hook regardless of topic -- rotate through the full set
    # instead, never repeating the immediately previous pick, so consecutive
    # uploads do not read as the same template with the words swapped out.
    from backend import ROTATING_HOOK_STYLES
    last_hook = None

    results = []
    for i in range(count):
        label = slot_name if count == 1 else f"{slot_name} - video {i + 1}/{count}"

        # Decide this video's topic source.
        if topic_source == "curiosity" or (topic_source == "mixed" and signals is None):
            use_curiosity = True
        elif topic_source == "mixed":
            use_curiosity = random.random() < 0.5
        else:
            use_curiosity = False

        context = ""
        if use_curiosity:
            pick = select_curiosity_topic(exclude_topics=used_topics, category=curiosity_category)
            if not pick:
                print(f"[agent] No fresh curiosity topic found for video {i + 1}; stopping early.")
                break
            topic = pick["title"]
            rationale = f"Curated curiosity topic — {pick['category']}."
            context = pick.get("hook", "")
        else:
            try:
                import trend_analyser
                picks = trend_analyser.analyse(
                    geo=region, model=ollama_model, count=1, used_topics=used_topics,
                    performance_hint=performance_hint, signals=signals, focus=channel_niche,
                )
                topic, rationale, context = picks[0]["title"], picks[0]["rationale"], picks[0]["rationale"]
            except Exception as e:
                print(f"[agent] Trend analysis failed for video {i + 1} ({e}); "
                     "falling back to a curiosity topic for this one.")
                pick = select_curiosity_topic(exclude_topics=used_topics, category=curiosity_category)
                if not pick:
                    print(f"[agent] No fresh topic available for video {i + 1}; stopping early.")
                    break
                topic, rationale, context = pick["title"], f"Curated curiosity topic — {pick['category']}.", pick.get("hook", "")

        hook_style = random.choice([h for h in ROTATING_HOOK_STYLES if h != last_hook] or ROTATING_HOOK_STYLES)
        last_hook = hook_style

        used_topics.insert(0, topic)  # so the next video avoids it
        results.append(_run_single_video(topic, rationale, label, config, ollama_model, all_logs,
                                         context=context, hook_style=hook_style,
                                         duration_preset=config.get("duration_preset")))

    return results[0] if results else None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trigger Viral Agent Run manually.")
    parser.add_argument("--dry-run", action="store_true", help="Perform topic selection and search grounding, but skip render & upload.")
    args = parser.parse_args()
    
    config = load_scheduler_config()
    
    if args.dry_run:
        print("Starting Viral Agent Dry Run...")
        trends = fetch_google_trends(config.get("region", "US"))
        print(f"Retrieved {len(trends)} trends.")
        topic, rationale = select_viral_topic(trends, config.get("model", "deepseek-v4-pro:cloud"))
        print(f"Selected Topic: {topic}")
        print(f"Rationale: {rationale}")
        if topic:
            grounding = get_web_grounding_context(topic, config.get("model", "deepseek-v4-pro:cloud"))
            print("Web Search Grounding Context retrieved.")
    else:
        run_viral_agent_job("Manual Trigger", config)
