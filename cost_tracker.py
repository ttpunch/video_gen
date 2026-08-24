"""Cost tracking and daily budget guard for paid generation APIs.

An unattended scheduler that retries failed Leonardo calls can quietly burn
through credits. Every image/motion generation is recorded, and a render is
refused up-front if it would push today's spend past the configured ceiling.

Configuration (all optional, via environment):
    LEONARDO_DAILY_BUDGET   Daily ceiling in cost units. Unset or <= 0 disables the guard.
    LEONARDO_IMAGE_COST     Cost charged per image generation   (default 1.0).
    LEONARDO_MOTION_COST    Cost charged per motion generation  (default 5.0).
"""
import os

import db_manager

_DEFAULT_COSTS = {"image": 1.0, "motion": 5.0}


class BudgetExceededError(Exception):
    """Raised when a generation would exceed the configured daily budget."""


def operation_cost(operation: str) -> float:
    """Cost of a single operation, overridable via ``LEONARDO_<OP>_COST``."""
    env_key = f"LEONARDO_{operation.upper()}_COST"
    try:
        return float(os.getenv(env_key, _DEFAULT_COSTS.get(operation, 0.0)))
    except (TypeError, ValueError):
        return _DEFAULT_COSTS.get(operation, 0.0)


def get_daily_budget():
    """Return the configured daily budget, or None when the guard is disabled."""
    raw = (os.getenv("LEONARDO_DAILY_BUDGET") or "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return val if val > 0 else None


def record(generation_id, operation, service="leonardo", cost=None):
    """Persist the cost of one operation and return the amount recorded."""
    amount = operation_cost(operation) if cost is None else float(cost)
    db_manager.record_api_cost(generation_id, service, operation, amount)
    return amount


def estimate_render_cost(num_scenes, visual_mode):
    """Estimate the spend for a render so it can be checked before any API call."""
    per_scene = operation_cost("image")
    if visual_mode in ("Leonardo Motion Video", "Hailuo Animated Video"):
        per_scene += operation_cost("motion")
    return per_scene * max(0, num_scenes)


def assert_within_budget(additional, service="leonardo", daily_budget=None):
    """Raise BudgetExceededError if spending ``additional`` would break the budget.

    No-op when no budget is configured.
    """
    budget = daily_budget if daily_budget is not None else get_daily_budget()
    if budget is None:
        return
    spent = db_manager.get_spend_today(service)
    if spent + additional > budget:
        raise BudgetExceededError(
            f"Daily {service} budget of {budget:.2f} would be exceeded: "
            f"already spent {spent:.2f}, this render needs ~{additional:.2f}."
        )
