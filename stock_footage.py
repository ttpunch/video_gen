"""Real stock footage from Pexels — the free path to visuals that aren't AI-fake.

Extracted from the (now removed) long-form pipeline, where this only ever ran in
landscape. It is kept because it is the highest-leverage fix available for the
shorts pipeline: generated people come out with distorted hands and melted faces,
while filmed people do not, and Pexels serves vertical clips at 1080x1920 and
2160x3840 — at or above delivery size, so real footage needs *zero* upscaling.
For comparison the free hosted image APIs cap at 576x1024, a 1.88x blow-up.

Free tier: 25,000 requests/month, no cost, key in PEXELS_API_KEY.

The search cascade matters. A scene's cinematic ``visual_prompt`` ("a lone
goalkeeper silhouetted against stadium floodlights, dramatic rim lighting") gets
zero stock matches, because stock libraries index short literal nouns. So each
query is retried progressively broader rather than failing outright.
"""
import os
import random
import time
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env here rather than relying on the importer having done it. This module
# reads PEXELS_API_KEY at call time, and when the key is absent it degrades
# *silently* -- returning None so the caller falls back to AI generation. That
# made a missing dotenv load indistinguishable from "no stock footage matched",
# which is exactly the failure that is hardest to notice in a rendered video.
load_dotenv()

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

#: Vertical delivery. Pexels calls this "portrait".
PORTRAIT = "portrait"
LANDSCAPE = "landscape"


def get_api_key(explicit: Optional[str] = None) -> str:
    return (explicit or os.getenv("PEXELS_API_KEY") or "").strip()


def search_pexels_candidates(query: str, api_key: str, orientation: str = PORTRAIT,
                             min_height: int = 0, per_page: int = 20,
                             log=print) -> list:
    """Return usable clips for ``query`` as a list of ``(video_id, url, height)``.

    Returns *candidates* rather than a single winner. Picking only the biggest
    match made selection deterministic: the same topic returned the same clip on
    every render, so a channel posting repeatedly around one subject got visibly
    recycled footage. Handing the caller a pool lets it skip anything already
    used in this video and vary its choice between renders.
    """
    if not api_key:
        log("[Pexels] API key is missing.")
        return []

    params = {"query": query, "per_page": per_page, "orientation": orientation}
    try:
        log(f"[Pexels] Searching: '{query}' ({orientation})")
        response = requests.get(PEXELS_SEARCH_URL, headers={"Authorization": api_key},
                                params=params, timeout=15)
    except requests.RequestException as e:
        log(f"[Pexels] Search error: {e}")
        return []

    if response.status_code != 200:
        log(f"[Pexels] API error {response.status_code}: {response.text[:160]}")
        return []

    videos = response.json().get("videos", [])
    if not videos:
        log(f"[Pexels] No results for '{query}'")
        return []

    # One entry per video (its largest qualifying rendition), so the pool is a
    # choice between distinct *clips*, not between encodes of the same clip.
    candidates = []
    for video in videos:
        best_url, best_h = None, -1
        for f in video.get("video_files", []):
            if f.get("file_type") != "video/mp4":
                continue
            h = f.get("height") or 0
            if h < min_height:
                continue
            if h > best_h:
                best_url, best_h = f.get("link"), h
        if best_url:
            candidates.append((video.get("id"), best_url, best_h))

    if not candidates:
        log(f"[Pexels] No clip met the {min_height}px floor for '{query}'.")
    return candidates


def search_pexels_video(query: str, api_key: str, orientation: str = PORTRAIT,
                        min_height: int = 0, log=print) -> Optional[str]:
    """Single best clip URL for ``query``. Kept for callers that want one result."""
    candidates = search_pexels_candidates(query, api_key, orientation, min_height, log=log)
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c[2])
    log(f"[Pexels] Selected a {best[2]}px-tall clip.")
    return best[1]


def download_video_file(url: str, output_path: str, max_retries: int = 3,
                        log=print) -> bool:
    """Stream a clip to disk, retrying on transient failures."""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, stream=True, timeout=45)
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True
            else:
                log(f"[Pexels] Download failed: HTTP {response.status_code}")
        except requests.RequestException as e:
            log(f"[Pexels] Download error (attempt {attempt}): {e}")
        time.sleep(3 * attempt)
    return False


def fetch_clip(query: str, output_path: str, api_key: Optional[str] = None,
               global_focus: str = "", orientation: str = PORTRAIT,
               min_height: int = 0, used_ids: Optional[set] = None,
               variety_seed: Optional[int] = None, log=print) -> Optional[str]:
    """Find and download one clip, widening the query until something matches.

    ``used_ids`` is a mutable set of Pexels video ids already used *in this
    video*; matching clips are skipped and the chosen id is added to it. Without
    it, two scenes whose queries overlap (and every scene that falls through to
    the generic backdrop, which always resolved to the same clip) could show
    identical footage in one short.

    ``variety_seed`` varies which of the equally-good candidates is taken, so
    re-rendering the same topic does not return byte-identical footage. Pass a
    stable value (e.g. hash of the generation id) to keep a given render
    reproducible.

    Returns the path on success, None if every fallback missed — callers are
    expected to fall back to image generation rather than fail the render.
    """
    api_key = get_api_key(api_key)
    clean = query.replace(",", "").replace(".", "").replace(";", "").strip()
    if used_ids is None:
        used_ids = set()

    # Progressively broader: exact phrase -> first two words -> the video's
    # recurring subject -> a generic backdrop that always returns something.
    attempts = [clean]
    words = clean.split()
    if len(words) > 2:
        attempts.append(" ".join(words[:2]))
    if global_focus:
        attempts.append(global_focus)
    attempts.append("abstract background" if orientation == PORTRAIT else "abstract space")

    rng = random.Random(variety_seed) if variety_seed is not None else random
    for i, attempt in enumerate(attempts):
        if not attempt:
            continue
        if i:
            log(f"[Pexels] Fallback {i}: '{attempt}'")

        for floor in ([min_height, 0] if min_height else [0]):
            candidates = search_pexels_candidates(
                attempt, api_key, orientation, floor, log=log)
            fresh = [c for c in candidates if c[0] not in used_ids]
            if not fresh:
                if candidates:
                    log(f"[Pexels] All {len(candidates)} matches for '{attempt}' "
                        f"are already used in this video; widening.")
                continue

            # Choose among the best-resolution candidates rather than strictly
            # the single largest: at 1080x1920 delivery, anything past the floor
            # looks the same, so trading a few pixels for variety is free.
            fresh.sort(key=lambda c: c[2], reverse=True)
            top = [c for c in fresh if c[2] >= fresh[0][2] * 0.75] or fresh
            video_id, url, height = rng.choice(top)

            if download_video_file(url, output_path, log=log):
                used_ids.add(video_id)
                log(f"[Pexels] Selected a {height}px-tall clip "
                    f"({len(top)} candidates considered).")
                return output_path
    return None
