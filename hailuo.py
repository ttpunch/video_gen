"""MiniMax Hailuo text/image-to-video generation.

Generates a short animated clip from a prompt, optionally anchored to a
first-frame image (so the clip inherits the look of a pre-generated scene image,
e.g. a stickman frame). Kept as a standalone module (no FastAPI / torch deps) so
it stays unit-testable in isolation, like image_providers.py.

Flow (MiniMax official API, platform.minimax.io):
  1. POST /v1/video_generation        -> {"task_id": ...}
  2. GET  /v1/query/video_generation  -> {"status": ..., "file_id": ...}  (poll)
  3. GET  /v1/files/retrieve          -> {"file": {"download_url": ...}}
  4. download the mp4
"""
import base64
import os
import time

import requests

_DEFAULT_HOST = "https://api.minimax.io"
_MODEL = "video-01"


def _encode_first_frame(path):
    """Return a base64 data-URI for ``path``, or None if unusable."""
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else "png"
    return f"data:image/{mime};base64,{b64}"


def generate_hailuo_video(prompt, first_frame_path=None, timeout=600, poll_interval=10):
    """Generate one animated clip and return the path to the downloaded mp4.

    Raises ``RuntimeError`` if the API key is missing, generation fails, or it
    times out.
    """
    api_key = os.getenv("MINIMAX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "MINIMAX_API_KEY is not set - get a free key at platform.minimax.io to use Hailuo Animated Video."
        )
    host = os.getenv("MINIMAX_API_HOST", _DEFAULT_HOST).rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    payload = {"model": _MODEL, "prompt": prompt, "prompt_optimizer": True}
    data_uri = _encode_first_frame(first_frame_path)
    if data_uri:
        payload["first_frame_image"] = data_uri

    # 1. Submit
    resp = requests.post(f"{host}/v1/video_generation", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json() or {}
    task_id = body.get("task_id")
    if not task_id:
        # MiniMax returns HTTP 200 with a base_resp error (e.g. 1008 insufficient
        # balance, 1004 invalid key). Surface that reason cleanly.
        base = body.get("base_resp") or {}
        reason = base.get("status_msg") or resp.text[:200]
        raise RuntimeError(f"Hailuo submit failed: {reason}")

    # 2. Poll
    file_id = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        p = requests.get(f"{host}/v1/query/video_generation",
                         params={"task_id": task_id}, headers=headers, timeout=30)
        p.raise_for_status()
        data = p.json() or {}
        status = data.get("status")
        if status == "Success":
            file_id = data.get("file_id")
            break
        if status == "Fail":
            raise RuntimeError(f"Hailuo generation failed: {data}")
    if not file_id:
        raise RuntimeError("Hailuo generation timed out while polling for completion.")

    # 3. Retrieve download URL
    fr = requests.get(f"{host}/v1/files/retrieve",
                      params={"file_id": file_id}, headers=headers, timeout=30)
    fr.raise_for_status()
    download_url = ((fr.json() or {}).get("file") or {}).get("download_url")
    if not download_url:
        raise RuntimeError(f"Hailuo: retrieve returned no download_url: {fr.text[:200]}")

    # 4. Download
    vid = requests.get(download_url, timeout=120)
    vid.raise_for_status()
    out_path = os.path.abspath(os.path.join("temp", f"hailuo_{int(time.time() * 1000)}.mp4"))
    with open(out_path, "wb") as f:
        f.write(vid.content)
    return out_path
