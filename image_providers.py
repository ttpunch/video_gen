"""Pluggable image-generation backends.

The pipeline used to be hard-wired to Leonardo's cloud API. This abstracts the
"make me an image" step so it can be served by:

  * ``local``        - Stable Diffusion running on-device (see local_sd.py). No API,
                       no tokens, no cost. Best on Apple Silicon / CUDA.
  * ``pollinations`` - Free hosted Flux endpoint, no API key, no signup.
  * ``leonardo``     - Original cloud API (handled in backend.py).

Every backend returns ``(image_path, image_id_or_None)``. Only Leonardo returns an
image id (used for its motion-video feature); the others return None, so motion
mode is simply skipped for them.
"""
import os
import shutil
import subprocess
import time
import threading
from urllib.parse import quote

import requests

# Delivery frame size. Every provider's output is brought up to this before it
# reaches the video pipeline, so the Ken Burns stage is never the thing doing a
# big blind upscale.
DELIVERY_W, DELIVERY_H = 1080, 1920

#: What each provider can actually produce, measured rather than assumed.
#: Pollinations' free tier ignores the requested size and returns ~576x1024 no
#: matter what you ask for, so the pipeline plans around that instead of
#: pretending the request was honoured.
PROVIDER_MAX = {
    "pollinations": (576, 1024),
    # SDXL's tallest practical bucket for a 9:16 frame. Quoting its square
    # native size (1024x1024) here would understate the upscale, because a
    # vertical render never gets the full 1024 of width.
    "local": (768, 1344),
    "leonardo": (576, 1024),
}


def upscale_to_delivery(path, width=DELIVERY_W, height=DELIVERY_H, sharpen=1.0):
    """Bring a generated image up to delivery resolution, in place.

    Upscaling cannot invent detail -- measured on a real 576x1024 generation,
    Laplacian sharpness falls from ~379 to ~142 no matter which chain is used,
    because the same information is spread over 3.5x the pixels. What this does
    buy is control over *where* the softening happens: doing one good lanczos
    pass with a mild unsharp here beats letting the Ken Burns supersample do an
    uncontrolled 3.75x blow-up of an already-soft frame.

    The real fix for sharpness is generating larger in the first place (local
    SDXL); this is damage control for providers that cap out below delivery size.
    """
    if not path or not os.path.exists(path):
        return path
    chain = (f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={width}:{height}")
    if sharpen > 0:
        # Amount ~1.0 was the best sharpness-to-halo ratio in testing; past ~1.5
        # ringing around high-contrast edges starts to read as artificial.
        chain += f",unsharp=5:5:{sharpen:.2f}:5:5:0.0"

    tmp = f"{os.path.splitext(path)[0]}_up.png"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-vf", chain, tmp],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        # A failed upscale must never cost us the generated image.
        return path
    shutil.move(tmp, path)
    return path

# Serialize ALL image generation across the whole app. Free hosted APIs (e.g.
# Pollinations) reject parallel / rapid-fire requests, so we hold this lock for
# the full duration of each request and space consecutive requests apart. This
# guarantees a strict one-at-a-time pipeline even when multiple videos/renders
# run concurrently.
_IMAGE_LOCK = threading.Lock()
_last_request_at = [0.0]


def _min_interval(provider: str) -> float:
    """Minimum seconds between consecutive image requests for a provider."""
    if provider == "pollinations":
        default = "6"
    elif provider == "leonardo":
        default = "1"
    else:  # local server has no external rate limit
        default = "0"
    try:
        return float(os.getenv("IMAGE_REQUEST_INTERVAL", default))
    except ValueError:
        return float(default)


def _temp_path(prefix: str, ext: str = "png") -> str:
    return os.path.abspath(os.path.join("temp", f"{prefix}_{int(time.time() * 1000)}.{ext}"))


# --- Pollinations (free hosted, no key) ---
def build_pollinations_url(prompt, width, height, model="flux", seed=None) -> str:
    url = "https://image.pollinations.ai/prompt/" + quote(prompt)
    params = f"?width={int(width)}&height={int(height)}&model={model}&nologo=true"
    if seed is not None:
        params += f"&seed={int(seed)}"
    return url + params


def generate_pollinations(prompt, width=DELIVERY_W, height=DELIVERY_H, model=None, timeout=180):
    model = model or os.getenv("POLLINATIONS_MODEL", "flux")
    # The free tier silently clamps to ~576x1024 whatever you ask for, so the
    # request is made at the ratio it will honour rather than a size it won't.
    cap_w, cap_h = PROVIDER_MAX["pollinations"]
    req_w, req_h = min(width, cap_w), min(height, cap_h)
    url = build_pollinations_url(prompt, req_w, req_h, model)
    resp = requests.get(url, timeout=timeout)
    if resp.status_code != 200 or not resp.content:
        raise RuntimeError(f"Pollinations HTTP {resp.status_code}: {resp.text[:200]}")
    if "image" not in resp.headers.get("content-type", ""):
        raise RuntimeError(f"Pollinations returned non-image content: {resp.headers.get('content-type')}")
    path = _temp_path("scene_poll")
    with open(path, "wb") as f:
        f.write(resp.content)
    upscale_to_delivery(path, width, height)
    return path, None


# --- Local SD microservice (native, GPU; see sd_server.py) ---
def generate_local_via_server(prompt, width=DELIVERY_W, height=DELIVERY_H,
                              steps=None, guidance=None, negative_prompt=None,
                              timeout=600):
    base = os.getenv("SD_SERVER_URL", "http://localhost:8001").rstrip("/")
    # The server snaps this to the model's nearest trained aspect bucket; what
    # matters here is sending the delivery *ratio*, not the exact pixel count.
    payload = {"prompt": prompt, "width": int(width), "height": int(height)}
    if steps is not None:
        payload["steps"] = int(steps)
    if guidance is not None:
        payload["guidance"] = float(guidance)
    if negative_prompt is not None:
        payload["negative_prompt"] = negative_prompt
    try:
        resp = requests.post(f"{base}/generate", json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Cannot reach local SD server at {base} ({e}). Start it with: python sd_server.py"
        ) from e
    if resp.status_code != 200 or not resp.content:
        raise RuntimeError(f"Local SD server HTTP {resp.status_code}: {resp.text[:200]}")
    if "image" not in resp.headers.get("content-type", ""):
        raise RuntimeError(f"Local SD server returned non-image content: {resp.headers.get('content-type')}")
    path = _temp_path("scene_local")
    with open(path, "wb") as f:
        f.write(resp.content)
    upscale_to_delivery(path, width, height)
    return path, None


# --- Dispatch ---
def resolve_provider(explicit=None) -> str:
    return (explicit or os.getenv("IMAGE_PROVIDER") or "leonardo").lower()


def generate_image(provider, prompt, width=DELIVERY_W, height=DELIVERY_H, **opts):
    """Generate one image with the chosen provider. Returns ``(path, image_id|None)``.

    All requests are serialized and throttled (see ``_IMAGE_LOCK``) so free APIs
    never receive parallel or back-to-back requests.
    """
    provider = (provider or "pollinations").lower()
    interval = _min_interval(provider)

    # Hold the lock for the whole request => true one-at-a-time pipeline.
    with _IMAGE_LOCK:
        wait = interval - (time.time() - _last_request_at[0])
        if wait > 0:
            time.sleep(wait)
        try:
            if provider == "pollinations":
                return generate_pollinations(prompt, width, height, **opts)
            if provider == "local":
                return generate_local_via_server(prompt, width, height, **opts)
            raise ValueError(
                f"Unknown image provider '{provider}'. Use 'local', 'pollinations', or 'leonardo'."
            )
        finally:
            _last_request_at[0] = time.time()
