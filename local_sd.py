"""On-device image generation with Stable Diffusion (diffusers).

A local, zero-cost replacement for Leonardo, and the only free path that can
produce genuinely sharp 1080x1920 frames -- the free hosted APIs cap out well
below delivery resolution.

Three things in here decide whether faces and bodies come out coherent:

  * **Model architecture vs. requested size.** A model renders cleanly only near
    the resolution it was trained at. The old default, ``stabilityai/sd-turbo``,
    is SD2.1-based and trained at 512x512; asking it for 576x1024 pushed it far
    outside that, which is what produced the melted skulls and elongated necks.
    SDXL models are trained at ~1024x1024 and have documented aspect buckets.
  * **Aspect buckets.** SDXL was fine-tuned on a specific set of width/height
    pairs. Requesting an arbitrary 9:16 size lands between buckets and degrades
    composition, so requests are snapped to the nearest supported bucket.
  * **Negative prompts.** Classifier-free guidance needs something to steer
    *away* from. Without one, anatomy artifacts have nothing pushing against
    them. Turbo models run at guidance 0.0, where a negative prompt has no
    effect at all -- which is the tradeoff for their speed.

Configuration (env):
    LOCAL_SD_MODEL      HF model id, or a key from ``MODEL_CATALOG``.
    LOCAL_SD_STEPS      Inference steps (default: per-model).
    LOCAL_SD_GUIDANCE   Guidance scale (default: per-model).
    LOCAL_SD_NEGATIVE   Override the default negative prompt.
    LOCAL_SD_DEVICE     'mps' | 'cuda' | 'cpu' (default: auto-detect).
    LOCAL_SD_DTYPE      'float16' | 'bfloat16' | 'float32' (default: per-device).
    HF_HOME             Model cache dir (default: ./models/hf_cache).
"""
import os
import time

# Cache multi-GB models on the project drive rather than the home volume.
_DEFAULT_CACHE = os.path.abspath(os.path.join(os.path.dirname(__file__), "models", "hf_cache"))
os.environ.setdefault("HF_HOME", _DEFAULT_CACHE)

#: Free, no-signup models worth offering, with the settings each one actually
#: wants. ``native`` is the edge length the model was trained at and drives
#: bucket selection; ``download_gb`` is what a first run costs.
MODEL_CATALOG = {
    "SDXL Turbo (fast, balanced)": {
        "id": "stabilityai/sdxl-turbo",
        "steps": 6, "guidance": 0.0, "native": 1024, "download_gb": 6.9,
        "note": "Few-step SDXL. Fast, and far more coherent than SD-Turbo. "
                "Runs at guidance 0, so negative prompts do not apply.",
    },
    "RealVis XL V5 (most photorealistic)": {
        "id": "SG161222/RealVisXL_V5.0",
        "steps": 28, "guidance": 6.0, "native": 1024, "download_gb": 6.9,
        "note": "SDXL fine-tuned for photorealism: the best free option for "
                "realistic faces and skin. Slowest of the three.",
    },
    "Juggernaut XL v9 (cinematic)": {
        "id": "RunDiffusion/Juggernaut-XL-v9",
        "steps": 25, "guidance": 5.5, "native": 1024, "download_gb": 6.9,
        "note": "SDXL fine-tune with a punchy cinematic look. Good middle "
                "ground between realism and drama.",
    },
    "SD Turbo (fastest, low quality)": {
        "id": "stabilityai/sd-turbo",
        "steps": 4, "guidance": 0.0, "native": 512, "download_gb": 2.5,
        "note": "512px SD2.1. Only sensible for quick drafts: it duplicates "
                "limbs and faces at the vertical sizes this app delivers.",
    },
}

#: SDXL's trained aspect buckets, as (width, height) at 1024-native. Scaled for
#: models with a different native size.
SDXL_BUCKETS = (
    (1024, 1024), (960, 1088), (896, 1152), (832, 1216),
    (768, 1344), (704, 1408), (640, 1536), (576, 1664),
)

#: Steers classifier-free guidance away from the failure modes that make an
#: AI-generated person read as fake: broken hands, duplicated limbs, waxy skin.
DEFAULT_NEGATIVE_PROMPT = (
    "deformed, distorted, disfigured, bad anatomy, wrong anatomy, malformed, "
    "mutated, mutilated, extra limbs, extra arms, extra legs, extra fingers, "
    "missing fingers, fused fingers, too many fingers, malformed hands, "
    "poorly drawn hands, poorly drawn face, elongated neck, long neck, "
    "asymmetric eyes, cross-eyed, plastic skin, waxy skin, doll-like, "
    "blurry, out of focus, lowres, jpeg artifacts, oversaturated, "
    "watermark, signature, text, caption, logo, frame, border, "
    "cartoon, anime, 3d render, cgi, illustration, painting"
)

DEFAULT_MODEL = "stabilityai/sdxl-turbo"
_PIPE = None
_PIPE_KEY = None


def resolve_model(name=None) -> str:
    """Accept either a catalog display name or a raw HF model id."""
    name = name or os.getenv("LOCAL_SD_MODEL") or DEFAULT_MODEL
    entry = MODEL_CATALOG.get(name)
    return entry["id"] if entry else name


def model_spec(model_id: str) -> dict:
    """Catalog entry for a model id, or a sane SDXL-shaped guess."""
    for entry in MODEL_CATALOG.values():
        if entry["id"].lower() == (model_id or "").lower():
            return entry
    lowered = (model_id or "").lower()
    is_turbo = "turbo" in lowered or "lightning" in lowered
    is_xl = "xl" in lowered or "sdxl" in lowered
    return {
        "id": model_id,
        "steps": 4 if is_turbo else 25,
        "guidance": 0.0 if is_turbo else 7.0,
        "native": 1024 if is_xl else 512,
        "note": "",
    }


def best_bucket(width: int, height: int, native: int = 1024):
    """Snap a requested size to the nearest trained aspect bucket.

    Off-bucket sizes are a documented source of duplicated subjects and broken
    composition in SDXL, so honouring the request exactly is worse than
    honouring its *aspect ratio*.
    """
    want = (width or 1) / (height or 1)
    scale = native / 1024
    best = min(SDXL_BUCKETS, key=lambda wh: abs((wh[0] / wh[1]) - want))
    return round_to_multiple(int(best[0] * scale)), round_to_multiple(int(best[1] * scale))


def resolve_device(explicit=None) -> str:
    if explicit:
        return explicit
    env = os.getenv("LOCAL_SD_DEVICE")
    if env:
        return env
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def default_steps(model_id: str) -> int:
    return 4 if "turbo" in model_id.lower() else 25


def default_guidance(model_id: str) -> float:
    return 0.0 if "turbo" in model_id.lower() else 7.0


def resolve_dtype(device: str, model_id: str = ""):
    """Pick the weight precision for a device and model.

    SDXL in float32 is ~14GB of weights, which does not fit alongside everything
    else on a 16GB machine, so defaulting MPS to fp32 locked this app out of
    SDXL entirely. fp16 lets it fit -- but SDXL's own VAE overflows fp16's
    numeric range during decode (non-deterministically: it can succeed once and
    then return solid black on the very next call), so get_pipeline() swaps in
    the community fp16-safe VAE for any XL model rather than trusting the
    stock one.

    SD 1.x/2.x are the exception and the reason this is not a flat rule: their
    VAE overflows fp16's range on MPS and silently produces an **all-black
    image with a zero exit status** -- measured, not theoretical. Those
    architectures stay on fp32, where they are small enough to fit anyway.
    """
    import torch

    override = os.getenv("LOCAL_SD_DTYPE")
    if override:
        return getattr(torch, override)
    lowered = (model_id or "").lower()
    is_xl = "xl" in lowered or model_spec(model_id).get("native", 1024) >= 1024
    if device != "cpu" and not is_xl:
        # Non-XL on a GPU backend: fp16 renders black, so pay the memory cost.
        return torch.float32
    if device == "cpu":
        return torch.float32
    return torch.float16


def round_to_multiple(value: int, multiple: int = 8) -> int:
    """SD requires width/height to be multiples of 8."""
    return max(multiple, int(round(value / multiple)) * multiple)


def get_pipeline(model_id=None, device=None):
    """Load (once) and return the diffusers text-to-image pipeline."""
    global _PIPE, _PIPE_KEY
    model_id = resolve_model(model_id)
    device = resolve_device(device)
    key = (model_id, device)
    if _PIPE is not None and _PIPE_KEY == key:
        return _PIPE

    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError as e:
        raise RuntimeError(
            "Local image generation needs diffusers. Install with: "
            "pip install diffusers transformers accelerate safetensors"
        ) from e

    dtype = resolve_dtype(device, model_id)
    load_kwargs = {"torch_dtype": dtype, "use_safetensors": True}
    # Prefer the fp16 weight files (what we run on MPS/CUDA). Without a variant,
    # diffusers also pulls the much larger fp32 weights. Fall back if a model
    # ships no fp16 variant.
    try:
        pipe = AutoPipelineForText2Image.from_pretrained(model_id, variant="fp16", **load_kwargs)
    except Exception as fp16_err:
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(model_id, **load_kwargs)
        except Exception as e:
            # A half-finished download leaves the config files in place but the
            # weights missing, and diffusers reports that as a bare "no file
            # named diffusion_pytorch_model.safetensors" that says nothing about
            # what to do. These are multi-GB fetches that routinely get
            # interrupted, so name the actual cause.
            spec = model_spec(model_id)
            size = spec.get("download_gb")
            raise RuntimeError(
                f"Could not load '{model_id}'. Its weights are missing or the "
                f"download was interrupted"
                f"{f' (~{size}GB total)' if size else ''}. "
                f"Re-run it with:\n"
                f"  python -c \"from huggingface_hub import snapshot_download; "
                f"snapshot_download('{model_id}')\"\n"
                f"Underlying error: {e}"
            ) from fp16_err
    # SDXL's stock VAE overflows fp16's numeric range during decode -- and it
    # does so non-deterministically. Measured directly on this pipeline: scene
    # 1 of a 3-scene render decoded fine, scenes 2 and 3 came back pure black
    # (RGB extrema (0, 0)) with diffusers logging "invalid value encountered in
    # cast" right at the pixel-decode step. The SD server's own log showed a
    # `upcast_vae` deprecation warning at the exact moment it happened -- that
    # was diffusers' legacy auto-recovery for this exact failure, and it no
    # longer fires reliably. Swapping in the community `sdxl-vae-fp16-fix`
    # checkpoint (retrained specifically so its activations never leave fp16
    # range) removes the failure mode outright rather than praying the
    # deprecated auto-upcast catches it.
    is_xl = "xl" in model_id.lower() or model_spec(model_id).get("native", 1024) >= 1024
    if is_xl and dtype == torch.float16:
        try:
            from diffusers import AutoencoderKL
            pipe.vae = AutoencoderKL.from_pretrained(
                "madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
        except Exception as vae_err:  # noqa: BLE001 - degrade, don't crash the load
            print(f"[local_sd] Could not load the fp16-safe SDXL VAE "
                  f"({vae_err}); falling back to fp32 VAE decode instead.")
            pipe.vae.to(torch.float32)
            pipe.upcast_vae = lambda: None  # already upcast; skip diffusers' own attempt

    pipe = pipe.to(device)
    # Keep memory footprint friendly for 16GB machines.
    for opt in ("enable_attention_slicing", "enable_vae_slicing"):
        try:
            getattr(pipe, opt)()
        except Exception:
            pass
    try:
        pipe.set_progress_bar_config(disable=True)
    except Exception:
        pass

    _PIPE, _PIPE_KEY = pipe, key
    return pipe


def render_image(prompt, width=1024, height=1024, steps=None, guidance=None,
                 negative_prompt=None, snap_to_bucket=True, _pipe=None):
    """Run the diffusion model and return a PIL image.

    ``_pipe`` is an injection point for tests; production loads the cached pipeline.
    """
    model_id = resolve_model()
    spec = model_spec(model_id)
    if steps is None:
        steps = int(os.getenv("LOCAL_SD_STEPS", spec["steps"]))
    if guidance is None:
        guidance = float(os.getenv("LOCAL_SD_GUIDANCE", spec["guidance"]))
    if negative_prompt is None:
        negative_prompt = os.getenv("LOCAL_SD_NEGATIVE", DEFAULT_NEGATIVE_PROMPT)

    if snap_to_bucket:
        width, height = best_bucket(width, height, spec["native"])
    else:
        width, height = round_to_multiple(width), round_to_multiple(height)

    pipe = _pipe or get_pipeline(model_id)

    # CLIP only handles 77 tokens; longer scene prompts otherwise crash the encoder.
    prompt = truncate_prompt(prompt, pipe)

    kwargs = dict(prompt=prompt, num_inference_steps=int(steps),
                  guidance_scale=float(guidance), width=width, height=height)
    # A negative prompt only does anything when guidance is on -- at guidance 0
    # (turbo models) the unconditional branch is never evaluated, and passing one
    # to a pipeline that does not accept it would be a hard error.
    if negative_prompt and float(guidance) > 0:
        kwargs["negative_prompt"] = truncate_prompt(negative_prompt, pipe)

    result = pipe(**kwargs)
    return result.images[0]


def truncate_prompt(prompt, pipe):
    """Trim a prompt to the CLIP tokenizer's max length (77 tokens)."""
    tokenizer = getattr(pipe, "tokenizer", None)
    if tokenizer is None:
        return prompt
    try:
        max_len = tokenizer.model_max_length
        ids = tokenizer(prompt, truncation=True, max_length=max_len).input_ids
        return tokenizer.decode(ids, skip_special_tokens=True)
    except Exception:
        return prompt


def render_to_bytes(prompt, width=1024, height=1024, steps=None, guidance=None,
                    negative_prompt=None, _pipe=None) -> bytes:
    """Generate one image and return raw PNG bytes (used by the SD HTTP server)."""
    import io
    image = render_image(prompt, width, height, steps, guidance,
                         negative_prompt=negative_prompt, _pipe=_pipe)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def generate_local_image(prompt, width=1024, height=1024, steps=None, guidance=None,
                         negative_prompt=None, _pipe=None):
    """Generate one image locally and save it to temp/. Returns ``(path, None)``.

    In-process convenience path; the microservice uses ``render_to_bytes`` instead.
    """
    image = render_image(prompt, width, height, steps, guidance,
                         negative_prompt=negative_prompt, _pipe=_pipe)
    path = os.path.abspath(os.path.join("temp", f"scene_local_{int(time.time() * 1000)}.png"))
    image.save(path)
    return path, None
