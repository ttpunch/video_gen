#!/usr/bin/env python3
import os
import sys
import time
import argparse
import random
import json
import shutil
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add current folder to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from backend import (
    run_viral_shorts_pipeline_new, get_ollama_models, KOKORO_VOICES, LEONARDO_MODELS,
    VIRAL_HOOKS, SATISFYING_PRESETS
)
import soundfile as sf

VIRAL_NICHES = {
    "Science Secrets": [
        "The bizarre quantum phenomenon of quantum entanglement",
        "Why time actually runs slower at the top of a mountain",
        "The hidden structure of water molecules under extreme pressure",
        "How black holes eventually evaporate through Hawking radiation"
    ],
    "Space Mysteries": [
        "The giant ocean hidden beneath the ice of Jupiter's moon Europa",
        "The dark matter halo surrounding our Milky Way galaxy",
        "What happens inside the event horizon of a supermassive black hole",
        "The mysterious radio signals known as Fast Radio Bursts"
    ],
    "Untold History": [
        "The ancient mechanical computer known as the Antikythera mechanism",
        "How the Library of Alexandria was actually lost to history",
        "The hidden underground city of Derinkuyu in Turkey",
        "The legendary bronze mirrors of ancient China that project images"
    ],
    "Nature Anomalies": [
        "The biological immortality of the Turritopsis dohrnii jellyfish",
        "The glowing blue waves caused by bioluminescent dinoflagellates",
        "How trees communicate and share nutrients through underground fungi networks",
        "The mysterious death valley stones that slide across the desert floor alone"
    ]
}

def main():
    parser = argparse.ArgumentParser(description="Generate daily 15-second YouTube Shorts / Instagram Reels headlessly.")
    parser.add_argument("--topic", type=str, default=None, help="The video topic. If not provided, a random topic is selected.")
    parser.add_argument("--niche", type=str, choices=list(VIRAL_NICHES.keys()), default=None, help="Force a specific niche.")
    parser.add_argument("--visual-mode", type=str, choices=["Cinematic Slideshow", "Leonardo Motion Video"], default="Cinematic Slideshow", help="Visual format.")
    parser.add_argument("--music", type=str, default="Cinematic", help="Background music style.")
    parser.add_argument("--voice", type=str, default="Sarah (Female - US - Soft)", help="Kokoro voice key.")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed.")
    parser.add_argument("--ollama-model", type=str, default=None, help="Ollama model to use.")
    parser.add_argument("--leonardo-model", type=str, default="Lucid Realism (High Quality Face)", help="Leonardo model.")
    
    # New Viral Upgrade arguments
    parser.add_argument("--hook-style", type=str, choices=list(VIRAL_HOOKS.keys()), default="Did You Know? (Fact Hook)", help="The script opening hook style.")
    parser.add_argument("--satisfying-bg", type=str, choices=["None"] + list(SATISFYING_PRESETS.keys()), default="None", help="Split-screen satisfying background video preset.")
    parser.add_argument("--disable-captions", action="store_true", help="Disable burning subtitles in the center.")
    parser.add_argument("--caption-font", type=str, default="Arial", help="Font for subtitles.")
    parser.add_argument("--caption-size", type=int, default=42, help="Font size for subtitles.")
    
    args = parser.parse_args()

    # Determine topic
    niche = args.niche
    topic = args.topic
    if not topic:
        if not niche:
            niche = random.choice(list(VIRAL_NICHES.keys()))
        topic = random.choice(VIRAL_NICHES[niche])
        print(f"No topic provided. Selected niche '{niche}' with topic: '{topic}'")
    else:
        print(f"Generating video for topic: '{topic}'")

    # Determine Ollama Model
    ollama_model = args.ollama_model
    if not ollama_model:
        models = get_ollama_models()
        ollama_model = models[0] if models else "deepseek-v4-pro:cloud"
    print(f"Using Ollama Model: {ollama_model}")

    print("Running the automated viral shorts pipeline...")
    try:
        # Run the pipeline
        output_video, storyboard, final_topic = run_viral_shorts_pipeline_new(
            prompt=topic,
            model=ollama_model,
            hook_style=args.hook_style,
            visual_mode=args.visual_mode,
            leonardo_model=args.leonardo_model,
            voice=args.voice,
            speed=args.speed,
            music_style=args.music,
            satisfying_background=args.satisfying_bg,
            enable_captions=not args.disable_captions,
            caption_font=args.caption_font,
            caption_size=args.caption_size
        )
    except Exception as e:
        print(f"Error generating video: {e}")
        sys.exit(1)

    # Save to daily_reels output folder
    os.makedirs(os.path.join("outputs", "daily_reels"), exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dest = os.path.abspath(os.path.join("outputs", "daily_reels", f"reel_{timestamp}.mp4"))
    
    # Copy from temp folder to final destination
    shutil.copy(output_video, final_dest)

    # Save log to history
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "topic": topic,
        "niche": niche or "Custom",
        "visual_mode": args.visual_mode,
        "music": args.music,
        "voice": args.voice,
        "output_path": final_dest,
        "storyboard": storyboard
    }

    history_path = os.path.abspath(os.path.join("outputs", "daily_reels", "history.json"))
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r") as hf:
                history = json.load(hf)
        except Exception:
            pass

    history.append(log_entry)
    with open(history_path, "w") as hf:
        json.dump(history, hf, indent=2)

    print("\n" + "="*50)
    print("SUCCESS: Daily video generated successfully!")
    print(f"Saved to: {final_dest}")
    print("="*50)

if __name__ == "__main__":
    main()
