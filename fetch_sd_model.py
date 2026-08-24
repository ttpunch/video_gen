#!/usr/bin/env python3
"""Download a local image model, resuming after interruptions.

The image models are 3-7GB. A plain ``snapshot_download`` on an unauthenticated
connection routinely stalls partway, and diffusers then reports the half-finished
cache as a bare "no file named diffusion_pytorch_model.safetensors" -- which
looks like a code bug rather than an incomplete download.

This retries with backoff and reports progress, so an interrupted fetch resumes
from where it stopped instead of starting over.

Usage:
    python fetch_sd_model.py                       # the configured default model
    python fetch_sd_model.py "RealVis XL V5 (most photorealistic)"
    python fetch_sd_model.py SG161222/RealVisXL_V5.0
    python fetch_sd_model.py --list
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

import local_sd  # noqa: E402  (sets HF_HOME on import)

# fp16 weights are what we actually run; without this filter the fetch also
# pulls the fp32 copies and roughly doubles the download.
ALLOW = ["*.json", "*.txt", "*fp16.safetensors",
         "*/*.json", "*/*.txt", "*/*fp16.safetensors"]


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def cached_bytes(model_id):
    root = os.path.join(os.environ["HF_HOME"], "hub",
                        "models--" + model_id.replace("/", "--"))
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".incomplete"):
                continue
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def fetch(model_id, attempts=6):
    from huggingface_hub import snapshot_download

    spec = local_sd.model_spec(model_id)
    print(f"Model    : {model_id}")
    print(f"Expected : ~{spec.get('download_gb', '?')}GB (fp16 weights only)")
    print(f"Cache    : {os.environ['HF_HOME']}\n")

    delay = 5
    for attempt in range(1, attempts + 1):
        before = cached_bytes(model_id)
        try:
            path = snapshot_download(model_id, allow_patterns=ALLOW, max_workers=4)
            print(f"\nComplete: {path}")
            print(f"On disk : {human(cached_bytes(model_id))}")
            return 0
        except KeyboardInterrupt:
            print("\nInterrupted. Re-run this script to resume.")
            return 130
        except Exception as e:  # noqa: BLE001 - any network failure is retryable
            gained = cached_bytes(model_id) - before
            print(f"\nAttempt {attempt}/{attempts} stopped after {human(gained)}: "
                  f"{type(e).__name__}: {str(e)[:160]}")
            if attempt == attempts:
                print("\nGiving up. Progress is kept -- re-run to resume.")
                return 1
            print(f"Retrying in {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return 1


def main(argv):
    if "--list" in argv:
        print("Available models:\n")
        for name, entry in local_sd.MODEL_CATALOG.items():
            print(f"  {name}")
            print(f"    id={entry['id']}  ~{entry['download_gb']}GB  "
                  f"{entry['steps']} steps  native={entry['native']}px")
            print(f"    {entry['note']}\n")
        return 0

    requested = argv[1] if len(argv) > 1 else None
    return fetch(local_sd.resolve_model(requested))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
