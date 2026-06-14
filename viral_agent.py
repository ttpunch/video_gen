#!/usr/bin/env python3
import os
import sys
import time
import json
import uuid
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add current folder to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

import db_manager
from backend import run_viral_shorts_pipeline_new, generate_ollama_script
from search_helper import get_web_grounding_context
from uploader_youtube import upload_video_to_youtube, is_youtube_authenticated

CONFIG_FILE = os.path.abspath("scheduler_config.json")
LOGS_FILE = os.path.abspath("scheduler_logs.json")

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

def select_viral_topic(trends_list, ollama_model):
    """Use Ollama LLM to select a safe, educational, high-engagement topic from the trends list."""
    if not trends_list:
        return None, "No trends available."
        
    url = f"http://localhost:11434/api/generate"
    
    # Strictly enforce safety filtering in LLM instructions to avoid strikes/violations
    system_prompt = (
        "You are an expert viral content strategist. "
        "Your task is to select the single best topic from the provided Google Trends list "
        "that would make an extremely interesting, educational, or highly engaging 15-second vertical video short/reel.\n\n"
        "STRICT SAFETY FILTERING RULES:\n"
        "1. Reject and skip any topics related to: violence, accidents, death, natural disasters, crime, political controversies, scandals, wars, or adult themes.\n"
        "2. Reject and skip any medical or health advice/claims (to avoid YouTube medical misinformation strikes).\n"
        "3. Prefer niches like: space discoveries, fascinating historical events, amazing science facts, technology innovations, or nature wonders.\n"
        "4. Avoid transient celebrity gossip or sports scores unless they have an educational science/history angle.\n\n"
        "Respond ONLY with a valid JSON object matching this exact format, with no markdown code fences, no conversational filler, and no extra text:\n"
        "{\n"
        "  \"topic\": \"The exact chosen topic name, refined for vertical short title\",\n"
        "  \"rationale\": \"A short 1-sentence explanation of why this is a safe, high-engagement topic\"\n"
        "}"
    )
    
    trends_text = ""
    for idx, item in enumerate(trends_list[:12]):
        trends_text += f"{idx+1}. Topic: {item['title']}, Traffic: {item['traffic']}, News: {item['summary']}\n"
        
    full_prompt = f"System: {system_prompt}\nTrends List:\n{trends_text}"
    
    payload = {
        "model": ollama_model,
        "prompt": full_prompt,
        "stream": False,
        "format": "json"
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

def run_viral_agent_job(slot_name, config=None):
    """Executes the complete autonomous viral generation & publishing loop."""
    if not config:
        config = load_scheduler_config()
        
    job_id = str(uuid.uuid4())
    execution_logs = []
    
    def log_step(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        print(entry)
        execution_logs.append(entry)
        
    log_step(f"Starting Viral Agent Run for slot: {slot_name}")
    
    # Setup log entry structure
    log_entry = {
        "id": job_id,
        "timestamp": datetime.now().isoformat() + "Z",
        "slot": slot_name,
        "topic": "Pending Selection",
        "status": "running",
        "video_path": None,
        "youtube_id": None,
        "logs": execution_logs
    }
    
    # Save log immediately as running
    all_logs = load_scheduler_logs()
    all_logs.insert(0, log_entry)
    save_scheduler_logs(all_logs)
    
    try:
        # 1. Fetch trends
        region = config.get("region", "US")
        log_step(f"Fetching Google Trends for region: {region}...")
        trends = fetch_google_trends(region)
        if not trends:
            raise Exception("No trending search topics retrieved from Google Trends.")
            
        log_step(f"Retrieved {len(trends)} trends. Selecting best safe topic...")
        
        # 2. Select topic
        ollama_model = config.get("model", "deepseek-v4-pro:cloud")
        topic, rationale = select_viral_topic(trends, ollama_model)
        if not topic:
            raise Exception("Ollama failed to select a safe trending topic.")
            
        log_step(f"Selected Topic: '{topic}'")
        log_step(f"Rationale: {rationale}")
        
        # Update log entry topic
        log_entry["topic"] = topic
        save_scheduler_logs(all_logs)
        
        # 3. Web search grounding
        log_step("Performing real-time Web Search Grounding for factual verification...")
        grounding_data = get_web_grounding_context(topic, ollama_model)
        web_context = grounding_data.get("context", "")
        if web_context:
            log_step(f"Factual grounding context retrieved successfully (query: '{grounding_data.get('search_query')}').")
        else:
            log_step("No web grounding context retrieved. Proceeding with LLM knowledge base.")
            
        # 4. Draft script & storyboard
        log_step("Drafting script and segmenting storyboard scenes...")
        script_data = generate_ollama_script(topic, ollama_model, hook_style="Did You Know? (Fact Hook)", enable_search=bool(web_context))
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
            custom_script_data=script_data
        )
        
        log_step(f"Video rendering completed successfully! Final Path: {final_video}")
        
        # Update db generation status
        db_manager.update_video_generation(
            gen_id, storyboard=final_storyboard, final_video_path=final_video, status="completed"
        )
        
        log_entry["video_path"] = final_video
        save_scheduler_logs(all_logs)
        
        # 7. Upload to YouTube (if credentials exist)
        log_step("Checking YouTube OAuth authorization...")
        if is_youtube_authenticated():
            log_step("YouTube credentials authenticated. Starting video upload...")
            
            yt_meta = script_data.get("youtube_metadata") or {}
            yt_title = yt_meta.get("title", f"{topic} #shorts #viral")
            if "#shorts" not in yt_title.lower():
                yt_title = f"{yt_title[:80]} #shorts"
                
            yt_desc = yt_meta.get("description", "Daily educational shorts.") + "\n\n#shorts #trending #facts"
            yt_tags = yt_meta.get("tags") or ["shorts", "facts", "viral"]
            privacy_status = config.get("privacy", "private")
            
            def upload_progress(pct):
                log_step(f"YouTube Upload Progress: {pct}%")
                
            yt_video_id = upload_video_to_youtube(
                final_video,
                title=yt_title,
                description=yt_desc,
                tags=yt_tags,
                privacy_status=privacy_status,
                progress_callback=upload_progress
            )
            
            log_step(f"YouTube Upload Successful! Video ID: {yt_video_id}")
            log_entry["youtube_id"] = yt_video_id
            
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
            
        log_step("Daily Auto-Agent run completed successfully!")
        log_entry["status"] = "success"
        
    except Exception as e:
        log_step(f"❌ ERROR: Daily Auto-Agent run failed: {str(e)}")
        log_entry["status"] = "failed"
        
    save_scheduler_logs(all_logs)
    return log_entry

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
