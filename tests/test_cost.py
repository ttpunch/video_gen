import uuid

import pytest

import db_manager
import cost_tracker


def test_operation_cost_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("LEONARDO_IMAGE_COST", raising=False)
    assert cost_tracker.operation_cost("image") == 1.0
    assert cost_tracker.operation_cost("motion") == 5.0

    monkeypatch.setenv("LEONARDO_IMAGE_COST", "0.25")
    assert cost_tracker.operation_cost("image") == 0.25


def test_get_daily_budget(monkeypatch):
    monkeypatch.delenv("LEONARDO_DAILY_BUDGET", raising=False)
    assert cost_tracker.get_daily_budget() is None

    monkeypatch.setenv("LEONARDO_DAILY_BUDGET", "0")
    assert cost_tracker.get_daily_budget() is None  # 0 disables the guard

    monkeypatch.setenv("LEONARDO_DAILY_BUDGET", "12.5")
    assert cost_tracker.get_daily_budget() == 12.5

    monkeypatch.setenv("LEONARDO_DAILY_BUDGET", "garbage")
    assert cost_tracker.get_daily_budget() is None


def test_estimate_render_cost(monkeypatch):
    monkeypatch.delenv("LEONARDO_IMAGE_COST", raising=False)
    monkeypatch.delenv("LEONARDO_MOTION_COST", raising=False)
    # Slideshow: image only.
    assert cost_tracker.estimate_render_cost(7, "Cinematic Slideshow") == 7.0
    # Motion: image + motion per scene.
    assert cost_tracker.estimate_render_cost(3, "Leonardo Motion Video") == 18.0


def test_record_and_spend_today_isolated_by_service():
    service = f"svc_{uuid.uuid4().hex[:8]}"
    gid = str(uuid.uuid4())
    db_manager.record_api_cost(gid, service, "image", 2.0)
    db_manager.record_api_cost(gid, service, "image", 3.0)

    assert db_manager.get_spend_today(service) == 5.0
    assert db_manager.get_spend_for_generation(gid) == 5.0


def test_assert_within_budget_passes_under_limit(monkeypatch):
    monkeypatch.setattr(db_manager, "get_spend_today", lambda service=None: 4.0)
    # 4 spent + 5 additional = 9 <= 10 -> OK
    cost_tracker.assert_within_budget(5.0, daily_budget=10.0)


def test_assert_within_budget_raises_over_limit(monkeypatch):
    monkeypatch.setattr(db_manager, "get_spend_today", lambda service=None: 8.0)
    with pytest.raises(cost_tracker.BudgetExceededError):
        cost_tracker.assert_within_budget(5.0, daily_budget=10.0)


def test_assert_within_budget_noop_when_unset(monkeypatch):
    monkeypatch.delenv("LEONARDO_DAILY_BUDGET", raising=False)
    # No budget configured -> never raises regardless of spend.
    monkeypatch.setattr(db_manager, "get_spend_today", lambda service=None: 9999.0)
    cost_tracker.assert_within_budget(9999.0)
