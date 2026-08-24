import pytest

import image_providers as ip


def test_build_pollinations_url():
    url = ip.build_pollinations_url("a cat in space", 576, 1024, model="flux", seed=7)
    assert url.startswith("https://image.pollinations.ai/prompt/")
    assert "a%20cat%20in%20space" in url
    assert "width=576" in url and "height=1024" in url
    assert "model=flux" in url and "seed=7" in url


def test_resolve_provider_precedence(monkeypatch):
    monkeypatch.delenv("IMAGE_PROVIDER", raising=False)
    assert ip.resolve_provider() == "leonardo"          # default
    assert ip.resolve_provider("Local") == "local"      # explicit wins, lowercased
    monkeypatch.setenv("IMAGE_PROVIDER", "pollinations")
    assert ip.resolve_provider() == "pollinations"      # env used when no explicit


def test_generate_image_unknown_provider_raises():
    with pytest.raises(ValueError):
        ip.generate_image("midjourney", "prompt")


def test_generate_image_routes_to_local(monkeypatch):
    called = {}
    def fake_local(prompt, width=576, height=1024, **opts):
        called["args"] = (prompt, width, height)
        return ("/tmp/x.png", None)
    monkeypatch.setattr(ip, "generate_local_via_server", fake_local)
    path, image_id = ip.generate_image("local", "a prompt", 576, 1024)
    assert path == "/tmp/x.png" and image_id is None
    assert called["args"] == ("a prompt", 576, 1024)


def test_generate_pollinations_saves_image(monkeypatch, tmp_path):
    class FakeResp:
        status_code = 200
        content = b"\x89PNG\r\n\x1a\n fake"
        headers = {"content-type": "image/png"}
        text = ""
    monkeypatch.setattr(ip.requests, "get", lambda *a, **k: FakeResp())
    monkeypatch.setattr(ip, "_temp_path", lambda prefix, ext="png": str(tmp_path / "out.png"))

    path, image_id = ip.generate_pollinations("hello", 576, 1024)
    assert image_id is None
    with open(path, "rb") as f:
        assert f.read().startswith(b"\x89PNG")


def test_generate_pollinations_non_image_raises(monkeypatch):
    class FakeResp:
        status_code = 200
        content = b"<html>error</html>"
        headers = {"content-type": "text/html"}
        text = "error"
    monkeypatch.setattr(ip.requests, "get", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError):
        ip.generate_pollinations("hello")


def test_local_via_server_unreachable_gives_actionable_error(monkeypatch):
    def boom(*a, **k):
        raise ip.requests.exceptions.ConnectionError("refused")
    monkeypatch.setattr(ip.requests, "post", boom)
    with pytest.raises(RuntimeError, match="python sd_server.py"):
        ip.generate_local_via_server("prompt")


# --------------------------------------------------------------------------
# Delivery resolution
# --------------------------------------------------------------------------

def test_delivery_size_matches_the_video_frame():
    import video_quality as vq
    assert (ip.DELIVERY_W, ip.DELIVERY_H) == (vq.SHORT_W, vq.SHORT_H)


def test_pollinations_request_is_clamped_to_what_the_free_tier_honours(monkeypatch):
    """Asking the free tier for 1080x1920 returns ~576x1021 -- a size that is
    neither what was requested nor the right aspect. Request the ratio it will
    actually serve instead."""
    seen = {}

    class FakeResp:
        status_code = 200
        content = b"\x89PNG\r\n\x1a\n fake"
        headers = {"content-type": "image/png"}
        text = ""

    def fake_get(url, **kwargs):
        seen["url"] = url
        return FakeResp()

    monkeypatch.setattr(ip.requests, "get", fake_get)
    monkeypatch.setattr(ip, "_temp_path", lambda prefix, ext="png": "/tmp/ignored.png")
    monkeypatch.setattr(ip, "upscale_to_delivery", lambda p, *a, **k: p)

    ip.generate_pollinations("hello", ip.DELIVERY_W, ip.DELIVERY_H)
    cap_w, cap_h = ip.PROVIDER_MAX["pollinations"]
    assert f"width={cap_w}" in seen["url"]
    assert f"height={cap_h}" in seen["url"]


def test_generated_images_are_upscaled_to_delivery_size(monkeypatch, tmp_path):
    """Otherwise the Ken Burns stage does a blind 3.75x blow-up instead."""
    called = {}

    class FakeResp:
        status_code = 200
        content = b"\x89PNG\r\n\x1a\n fake"
        headers = {"content-type": "image/png"}
        text = ""

    monkeypatch.setattr(ip.requests, "get", lambda *a, **k: FakeResp())
    monkeypatch.setattr(ip, "_temp_path", lambda prefix, ext="png": str(tmp_path / "o.png"))
    monkeypatch.setattr(ip, "upscale_to_delivery",
                        lambda p, *a, **k: called.setdefault("path", p) or p)

    ip.generate_pollinations("hello")
    assert called.get("path") == str(tmp_path / "o.png")


def test_upscale_really_resizes_a_small_image(tmp_path):
    import subprocess

    import video_quality as vq

    small = tmp_path / "small.png"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=576x1024:d=1:r=1",
         "-frames:v", "1", str(small)],
        check=True, capture_output=True)

    ip.upscale_to_delivery(str(small))
    info = vq.probe(str(small))
    assert (info["width"], info["height"]) == (ip.DELIVERY_W, ip.DELIVERY_H)


def test_upscale_keeps_the_original_when_ffmpeg_fails(tmp_path):
    """A failed upscale must never cost us an image that took 30s to generate."""
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    assert ip.upscale_to_delivery(str(broken)) == str(broken)
    assert broken.read_bytes() == b"not a png"


def test_upscale_is_a_noop_for_a_missing_file():
    assert ip.upscale_to_delivery("/nonexistent/x.png") == "/nonexistent/x.png"


def test_provider_max_documents_every_provider():
    for provider in ("pollinations", "local", "leonardo"):
        w, h = ip.PROVIDER_MAX[provider]
        assert w > 0 and h > 0
