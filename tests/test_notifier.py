import os

import notifier


def test_build_telegram_request():
    url, payload = notifier.build_telegram_request("TOKEN", "CHAT", "hello")
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload["chat_id"] == "CHAT"
    assert payload["text"] == "hello"


def test_telegram_text_is_truncated():
    _, payload = notifier.build_telegram_request("t", "c", "x" * 5000)
    assert len(payload["text"]) <= 4000


def test_webhook_payload_supports_slack_and_discord():
    payload = notifier.build_webhook_payload("msg")
    assert payload["text"] == "msg"      # Slack
    assert payload["content"] == "msg"   # Discord


def test_notify_writes_log_and_is_noop_without_config(tmp_path, monkeypatch):
    log_file = tmp_path / "alerts.log"
    monkeypatch.setattr(notifier, "ALERT_LOG_FILE", str(log_file))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)

    result = notifier.notify("Subject", "Body", level="error")

    assert result["logged"] is True
    assert result["telegram"] is None
    assert result["webhook"] is None
    assert log_file.exists()
    assert "Subject" in log_file.read_text()


def test_notify_posts_to_telegram_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(notifier, "ALERT_LOG_FILE", str(tmp_path / "a.log"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOK")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)

    calls = []

    class FakeResp:
        status_code = 200

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResp()

    result = notifier.notify("S", "B", _poster=fake_post)

    assert result["telegram"] == 200
    assert len(calls) == 1
    assert "api.telegram.org/botTOK" in calls[0][0]


def test_notify_never_raises_when_poster_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(notifier, "ALERT_LOG_FILE", str(tmp_path / "a.log"))
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.com/hook")

    def boom(*a, **k):
        raise ConnectionError("network down")

    result = notifier.notify("S", "B", _poster=boom)
    assert result["logged"] is True
    assert "error" in str(result["webhook"])
