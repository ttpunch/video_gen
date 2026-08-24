import os

import pytest

import local_sd


def test_round_to_multiple():
    assert local_sd.round_to_multiple(576) == 576
    assert local_sd.round_to_multiple(1020) == 1024
    assert local_sd.round_to_multiple(3) == 8  # never below the multiple


def test_default_steps_and_guidance_for_turbo():
    assert local_sd.default_steps("stabilityai/sdxl-turbo") == 4
    assert local_sd.default_guidance("stabilityai/sdxl-turbo") == 0.0


def test_default_steps_and_guidance_for_non_turbo():
    assert local_sd.default_steps("stabilityai/stable-diffusion-xl-base-1.0") == 25
    assert local_sd.default_guidance("runwayml/stable-diffusion-v1-5") == 7.0


def test_resolve_device_respects_explicit_and_env(monkeypatch):
    monkeypatch.delenv("LOCAL_SD_DEVICE", raising=False)
    assert local_sd.resolve_device("cpu") == "cpu"
    monkeypatch.setenv("LOCAL_SD_DEVICE", "cuda")
    assert local_sd.resolve_device() == "cuda"


# --------------------------------------------------------------------------
# Model selection
# --------------------------------------------------------------------------

def test_default_model_is_sdxl_not_the_512px_one(monkeypatch):
    """sd-turbo is 512px-native; asking it for tall 9:16 frames is what
    produced the elongated, melted anatomy."""
    monkeypatch.delenv("LOCAL_SD_MODEL", raising=False)
    assert local_sd.model_spec(local_sd.resolve_model())["native"] == 1024


def test_resolve_model_accepts_catalog_names_and_raw_ids(monkeypatch):
    monkeypatch.delenv("LOCAL_SD_MODEL", raising=False)
    assert local_sd.resolve_model("SDXL Turbo (fast, balanced)") == "stabilityai/sdxl-turbo"
    assert local_sd.resolve_model("some/custom-model") == "some/custom-model"


def test_every_catalog_entry_is_complete():
    for name, entry in local_sd.MODEL_CATALOG.items():
        assert entry["id"] and entry["native"] in (512, 1024), name
        assert entry["steps"] > 0 and entry["guidance"] >= 0, name
        assert entry["note"], f"{name} needs a note explaining the tradeoff"


def test_model_spec_guesses_sensibly_for_unknown_models():
    spec = local_sd.model_spec("someone/MyRealisticXL_v3")
    assert spec["native"] == 1024
    assert spec["guidance"] > 0            # not a turbo model
    spec_turbo = local_sd.model_spec("someone/fast-turbo")
    assert spec_turbo["guidance"] == 0.0


# --------------------------------------------------------------------------
# Aspect buckets
# --------------------------------------------------------------------------

def test_vertical_request_snaps_to_the_tall_sdxl_bucket():
    w, h = local_sd.best_bucket(1080, 1920, native=1024)
    assert (w, h) == (768, 1344)
    assert w / h == pytest.approx(1080 / 1920, abs=0.02)


def test_square_request_snaps_to_the_square_bucket():
    assert local_sd.best_bucket(1024, 1024, native=1024) == (1024, 1024)


def test_buckets_scale_down_for_a_512px_model():
    w, h = local_sd.best_bucket(1080, 1920, native=512)
    assert (w, h) == (384, 672)
    assert w % 8 == 0 and h % 8 == 0


def test_all_buckets_are_diffusion_safe_multiples():
    for w, h in local_sd.SDXL_BUCKETS:
        assert w % 8 == 0 and h % 8 == 0


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, image):
        self.images = [image]


class _FakePipe:
    """Mimics a diffusers pipeline; records call kwargs."""

    def __init__(self):
        self.calls = []

    def __call__(self, prompt, num_inference_steps, guidance_scale, width, height,
                 negative_prompt=None):
        self.calls.append(dict(prompt=prompt, steps=num_inference_steps,
                               guidance=guidance_scale, width=width, height=height,
                               negative_prompt=negative_prompt))
        from PIL import Image
        return _FakeResult(Image.new("RGB", (width, height), (10, 20, 30)))


def test_render_to_bytes_with_injected_pipe(monkeypatch):
    monkeypatch.setenv("LOCAL_SD_MODEL", "stabilityai/sdxl-turbo")
    monkeypatch.delenv("LOCAL_SD_STEPS", raising=False)
    monkeypatch.delenv("LOCAL_SD_GUIDANCE", raising=False)
    pipe = _FakePipe()
    png = local_sd.render_to_bytes("a serene mountain", 1080, 1920, _pipe=pipe)
    assert png.startswith(b"\x89PNG")
    call = pipe.calls[0]
    assert call["steps"] == 6                       # catalog value for sdxl-turbo
    assert call["guidance"] == 0.0
    # The request was snapped to the nearest trained bucket, not passed through.
    assert (call["width"], call["height"]) == (768, 1344)


def test_negative_prompt_is_sent_when_guidance_is_on(monkeypatch):
    monkeypatch.setenv("LOCAL_SD_MODEL", "SG161222/RealVisXL_V5.0")
    monkeypatch.delenv("LOCAL_SD_STEPS", raising=False)
    monkeypatch.delenv("LOCAL_SD_GUIDANCE", raising=False)
    monkeypatch.delenv("LOCAL_SD_NEGATIVE", raising=False)
    pipe = _FakePipe()
    local_sd.render_image("a portrait", 1080, 1920, _pipe=pipe)
    neg = pipe.calls[0]["negative_prompt"]
    assert neg and "bad anatomy" in neg


def test_negative_prompt_is_skipped_at_zero_guidance(monkeypatch):
    """At guidance 0 the unconditional branch is never evaluated, so a negative
    prompt would do nothing but cost tokens."""
    monkeypatch.setenv("LOCAL_SD_MODEL", "stabilityai/sdxl-turbo")
    monkeypatch.delenv("LOCAL_SD_GUIDANCE", raising=False)
    pipe = _FakePipe()
    local_sd.render_image("a portrait", 1080, 1920, _pipe=pipe)
    assert pipe.calls[0]["negative_prompt"] is None


def test_negative_prompt_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("LOCAL_SD_MODEL", "SG161222/RealVisXL_V5.0")
    monkeypatch.setenv("LOCAL_SD_NEGATIVE", "custom negative")
    monkeypatch.delenv("LOCAL_SD_GUIDANCE", raising=False)
    pipe = _FakePipe()
    local_sd.render_image("a portrait", 1080, 1920, _pipe=pipe)
    assert pipe.calls[0]["negative_prompt"] == "custom negative"


def test_snap_to_bucket_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LOCAL_SD_MODEL", "stabilityai/sdxl-turbo")
    pipe = _FakePipe()
    local_sd.render_image("x", 640, 1152, snap_to_bucket=False, _pipe=pipe)
    assert (pipe.calls[0]["width"], pipe.calls[0]["height"]) == (640, 1152)


def test_generate_local_image_writes_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_SD_MODEL", "stabilityai/sdxl-turbo")
    pipe = _FakePipe()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "temp").mkdir()
    path, image_id = local_sd.generate_local_image("prompt", 1080, 1920, _pipe=pipe)
    assert image_id is None
    assert os.path.exists(path)


def test_sdxl_uses_fp16_on_gpu(monkeypatch):
    """SDXL in fp32 is ~14GB of weights, which does not fit on a 16GB machine."""
    import torch
    monkeypatch.delenv("LOCAL_SD_DTYPE", raising=False)
    assert local_sd.resolve_dtype("mps", "stabilityai/sdxl-turbo") == torch.float16
    assert local_sd.resolve_dtype("cuda", "SG161222/RealVisXL_V5.0") == torch.float16


def test_non_xl_models_stay_fp32_on_gpu(monkeypatch):
    """Measured: SD2.1 in fp16 on MPS renders an all-black image and exits 0.

    The VAE overflows fp16's range, so the failure is silent -- which is exactly
    why this needs a test rather than a comment.
    """
    import torch
    monkeypatch.delenv("LOCAL_SD_DTYPE", raising=False)
    assert local_sd.resolve_dtype("mps", "stabilityai/sd-turbo") == torch.float32
    assert local_sd.resolve_dtype("cuda", "runwayml/stable-diffusion-v1-5") == torch.float32


def test_cpu_and_env_override(monkeypatch):
    import torch
    monkeypatch.delenv("LOCAL_SD_DTYPE", raising=False)
    assert local_sd.resolve_dtype("cpu", "stabilityai/sdxl-turbo") == torch.float32
    monkeypatch.setenv("LOCAL_SD_DTYPE", "float32")
    assert local_sd.resolve_dtype("mps", "stabilityai/sdxl-turbo") == torch.float32


# --------------------------------------------------------------------------
# fp16-safe VAE swap
# --------------------------------------------------------------------------
#
# Regression guard for a real failure observed end-to-end: rendering 3 scenes
# through the actual `run_viral_shorts_pipeline_new` pipeline with SDXL-Turbo
# in fp16 on MPS produced a correct image for scene 1 and pure black
# (luminance extrema (0, 0)) for scenes 2 and 3, with diffusers logging
# "invalid value encountered in cast" at the pixel-decode step -- SDXL's stock
# VAE overflowing fp16's numeric range, non-deterministically. get_pipeline()
# now swaps in the community `sdxl-vae-fp16-fix` checkpoint for any XL model
# running in fp16; these tests pin that behaviour without needing real weights.

class _FakePipeForVaeSwap:
    def __init__(self):
        self.vae = _FakeVae()
        self.to_calls = []

    def to(self, device):
        self.to_calls.append(device)
        return self

    def set_progress_bar_config(self, **kw):
        pass


class _FakeVae:
    def __init__(self):
        self.dtype = None
        self.to_calls = []

    def to(self, dtype):
        self.to_calls.append(dtype)
        self.dtype = dtype


def _patch_pipeline_loading(monkeypatch, fake_pipe, vae_loader=None):
    import diffusers

    monkeypatch.setattr(
        diffusers, "AutoPipelineForText2Image",
        type("_Fake", (), {"from_pretrained": staticmethod(lambda *a, **k: fake_pipe)}),
        raising=False,
    )
    if vae_loader is not None:
        monkeypatch.setattr(
            diffusers, "AutoencoderKL",
            type("_FakeVaeCls", (), {"from_pretrained": staticmethod(vae_loader)}),
            raising=False,
        )
    monkeypatch.setattr(local_sd, "_PIPE", None)
    monkeypatch.setattr(local_sd, "_PIPE_KEY", None)


def test_xl_model_in_fp16_gets_the_fp16_safe_vae(monkeypatch):
    import torch

    fake_pipe = _FakePipeForVaeSwap()
    original_vae = fake_pipe.vae
    loaded_with = {}

    def fake_vae_loader(repo_id, **kwargs):
        loaded_with["repo_id"] = repo_id
        loaded_with["dtype"] = kwargs.get("torch_dtype")
        return _FakeVae()

    _patch_pipeline_loading(monkeypatch, fake_pipe, fake_vae_loader)
    monkeypatch.setenv("LOCAL_SD_DTYPE", "float16")
    monkeypatch.setenv("LOCAL_SD_DEVICE", "mps")

    local_sd.get_pipeline("stabilityai/sdxl-turbo")

    assert loaded_with.get("repo_id") == "madebyollin/sdxl-vae-fp16-fix", \
        "XL model in fp16 must load the community fp16-safe VAE"
    assert loaded_with.get("dtype") == torch.float16
    assert fake_pipe.vae is not original_vae, \
        "pipe.vae must be replaced with the loaded fp16-safe instance"


def test_non_xl_model_does_not_touch_the_vae(monkeypatch):
    """The swap is SDXL-specific; SD 1.x/2.x already run fp32 (see resolve_dtype)
    and never need it."""
    fake_pipe = _FakePipeForVaeSwap()
    original_vae = fake_pipe.vae
    calls = {"n": 0}

    def fake_vae_loader(*a, **k):
        calls["n"] += 1
        return _FakeVae()

    _patch_pipeline_loading(monkeypatch, fake_pipe, fake_vae_loader)
    monkeypatch.delenv("LOCAL_SD_DTYPE", raising=False)
    monkeypatch.setenv("LOCAL_SD_DEVICE", "mps")

    local_sd.get_pipeline("stabilityai/sd-turbo")

    assert calls["n"] == 0, "non-XL models must not trigger the VAE swap"
    assert fake_pipe.vae is original_vae


def test_vae_swap_failure_falls_back_to_fp32_upcast_instead_of_crashing(monkeypatch):
    """If the fp16-safe VAE can't be fetched (offline, HF hiccup), the load
    must still succeed -- degraded to fp32 VAE decode -- rather than raising."""
    import torch

    fake_pipe = _FakePipeForVaeSwap()

    def broken_vae_loader(*a, **k):
        raise RuntimeError("simulated network failure")

    _patch_pipeline_loading(monkeypatch, fake_pipe, broken_vae_loader)
    monkeypatch.setenv("LOCAL_SD_DTYPE", "float16")
    monkeypatch.setenv("LOCAL_SD_DEVICE", "mps")

    result = local_sd.get_pipeline("stabilityai/sdxl-turbo")

    assert result is fake_pipe
    assert torch.float32 in fake_pipe.vae.to_calls, \
        "must upcast the original VAE to fp32 when the fp16-safe swap fails"
