"""Single choke point for every text-generation call the app makes to an LLM.

Local Ollama stays the free, unlimited default. When OPENROUTER_API_KEY is set,
a model name containing "/" (OpenRouter's vendor/model convention -- no locally
installed Ollama tag uses one) is routed to OpenRouter's OpenAI-compatible chat
endpoint instead. Every existing "model" field in the app (scheduler config,
the UI's Ollama dropdown, DraftRequest) keeps working unchanged: picking an
OpenRouter model id there (e.g. "deepseek/deepseek-chat-v3.1:free") is the only
opt-in needed, no separate provider switch to thread through call sites.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

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

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.3-flash")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter's model catalog turns over fast -- entries here were confirmed live
# against https://openrouter.ai/api/v1/models. "glm-5.3-flash" is not on the
# free tier but is pay-per-token at $0.075/M input, $0.25/M output tokens: on
# this app's measured ~1000in/700out per call, that's a fraction of a cent per
# video, and it responded in 2-4s in testing vs. ~50-65s for local Ollama.
OPENROUTER_MODELS = [
    "z-ai/glm-5.3-flash",
    "z-ai/glm-5.2:free",
    "minimax/minimax-m3:free",
    "google/gemma-4-31b-it:free",
]


def is_openrouter_model(model: str) -> bool:
    return bool(OPENROUTER_API_KEY) and "/" in (model or "")


def _generate_openrouter(model: str, prompt: str, timeout: int, json_mode: bool) -> str:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter HTTP {r.status_code}: {r.text[:200]}")
    choices = r.json().get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {r.text[:200]}")
    return (choices[0].get("message", {}).get("content", "") or "").strip()


def _generate_ollama(model: str, prompt: str, timeout: int, json_mode: bool) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_ctx": OLLAMA_NUM_CTX},
    }
    if json_mode:
        payload["format"] = "json"
    r = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
    return (r.json().get("response", "") or "").strip()


def generate(model: str, prompt: str, timeout: int = 90, json_mode: bool = False) -> str:
    """Send ``prompt`` to whichever provider ``model`` names and return the
    raw text response. Raises RuntimeError on a non-200, empty, or timed-out
    response -- callers already wrap these calls in their own retry/fallback
    logic.

    Runs the actual HTTP call in a worker thread with a hard wall-clock
    deadline instead of trusting requests' own ``timeout`` to bound it.
    ``requests``/urllib3's timeout only bounds the gap *between* reads, not
    total request time: a slow provider that trickles keep-alive bytes (common
    behind a reverse proxy fronting a long-running LLM completion, to stop
    infra-level idle timeouts from killing the connection) can hold a request
    open far longer than the timeout implies. Measured live: a real
    OpenRouter call for this app's storyboard prompt hung past 400s with
    ``requests.post(..., timeout=120)`` in place and never returned -- the
    exact shape of this bug -- so an independent hard deadline is required,
    the same fix already applied to the DuckDuckGo search call for the same
    underlying reason.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

    target = _generate_openrouter if is_openrouter_model(model) else _generate_ollama
    # Not a context manager: `with` blocks on shutdown(wait=True) until the
    # submitted task finishes, which would silently reintroduce the same
    # indefinite hang this wrapper exists to prevent if the call never returns.
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(target, model, prompt, timeout, json_mode)
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        raise RuntimeError(
            f"LLM call to '{model}' exceeded the {timeout}s hard deadline with no response "
            "(the underlying HTTP request never raised its own timeout -- likely a slow "
            "provider trickling keep-alive bytes to hold the connection open)."
        )
    finally:
        pool.shutdown(wait=False)
