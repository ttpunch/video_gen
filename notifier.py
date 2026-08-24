"""Failure alerting for the autonomous pipeline.

An unattended scheduler that fails silently is worse than no scheduler. When a
render or upload job fails, ``notify()`` records the failure to a local log and
pushes it to any configured channel:

* Telegram  - set ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID``.
* Webhook   - set ``ALERT_WEBHOOK_URL`` (Slack- and Discord-compatible).

If nothing is configured, ``notify()`` still writes to ``failure_alerts.log`` and
returns without error, so callers never have to guard the call.
"""
import os
import json
from datetime import datetime

import requests

ALERT_LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "failure_alerts.log"))


def build_telegram_request(token: str, chat_id: str, text: str):
    """Return the ``(url, payload)`` tuple for a Telegram sendMessage call."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram caps messages at 4096 chars.
    payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    return url, payload


def build_webhook_payload(text: str) -> dict:
    """Return a payload that satisfies both Slack (``text``) and Discord (``content``)."""
    return {"text": text[:1900], "content": text[:1900]}


def _format(subject: str, message: str, level: str, context: dict | None) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(level, "\U0001f514")
    lines = [f"{icon} [{level.upper()}] {subject}", f"Time: {stamp}", "", message]
    if context:
        lines.append("")
        for k, v in context.items():
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _append_log(text: str) -> None:
    try:
        with open(ALERT_LOG_FILE, "a") as f:
            f.write(text + "\n" + ("-" * 60) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[notifier] could not write alert log: {e}")


def notify(subject, message, level="error", context=None, _poster=requests.post):
    """Send a failure/notification alert through every configured channel.

    Always writes to the local alert log. Never raises - alerting must not break
    the job it is reporting on. Returns a dict describing what was attempted.
    """
    text = _format(subject, message, level, context)
    _append_log(text)

    results = {"logged": True, "telegram": None, "webhook": None}

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            url, payload = build_telegram_request(token, chat_id, text)
            resp = _poster(url, data=payload, timeout=10)
            results["telegram"] = getattr(resp, "status_code", "sent")
        except Exception as e:  # noqa: BLE001
            results["telegram"] = f"error: {e}"
            print(f"[notifier] telegram alert failed: {e}")

    webhook = os.getenv("ALERT_WEBHOOK_URL")
    if webhook:
        try:
            resp = _poster(webhook, json=build_webhook_payload(text), timeout=10)
            results["webhook"] = getattr(resp, "status_code", "sent")
        except Exception as e:  # noqa: BLE001
            results["webhook"] = f"error: {e}"
            print(f"[notifier] webhook alert failed: {e}")

    print(text)
    return results
