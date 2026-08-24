"""MiniMax Hailuo video generation: submit -> poll -> retrieve -> download."""
import os

import pytest

import hailuo


class _FakeResp:
    def __init__(self, json_data=None, content=b"", status=200):
        self._json = json_data or {}
        self.content = content
        self.status_code = status
        self.text = str(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_generate_hailuo_video_returns_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp", exist_ok=True)

    def fake_post(url, **kwargs):
        assert "video_generation" in url
        return _FakeResp({"task_id": "task-123"})

    calls = {"poll": 0}

    def fake_get(url, **kwargs):
        if "query/video_generation" in url:
            calls["poll"] += 1
            return _FakeResp({"status": "Success", "file_id": "file-9"})
        if "files/retrieve" in url:
            return _FakeResp({"file": {"download_url": "http://x/v.mp4"}})
        # download
        return _FakeResp(content=b"FAKEMP4DATA")

    monkeypatch.setattr(hailuo.requests, "post", fake_post)
    monkeypatch.setattr(hailuo.requests, "get", fake_get)

    path = hailuo.generate_hailuo_video("a stick figure waves", poll_interval=0)
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"FAKEMP4DATA"


def test_generate_hailuo_video_raises_on_fail_status(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp", exist_ok=True)

    monkeypatch.setattr(hailuo.requests, "post", lambda url, **k: _FakeResp({"task_id": "t1"}))
    monkeypatch.setattr(hailuo.requests, "get",
                        lambda url, **k: _FakeResp({"status": "Fail", "base_resp": {"status_msg": "nope"}}))

    with pytest.raises(RuntimeError):
        hailuo.generate_hailuo_video("a stick figure waves", poll_interval=0)


def test_generate_hailuo_video_raises_if_no_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        hailuo.generate_hailuo_video("anything")


def test_generate_hailuo_video_surfaces_base_resp_error(tmp_path, monkeypatch):
    """A submit that returns an empty task_id + base_resp error (e.g. insufficient
    balance) must raise with the API's status_msg, not a generic message."""
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp", exist_ok=True)

    monkeypatch.setattr(hailuo.requests, "post", lambda url, **k: _FakeResp(
        {"task_id": "", "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"}}))

    with pytest.raises(RuntimeError, match="insufficient balance"):
        hailuo.generate_hailuo_video("a stick figure waves", poll_interval=0)
