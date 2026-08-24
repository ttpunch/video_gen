"""Tests for competitor view-velocity mining (what format is hot right now)."""
import datetime
import uuid

import competitor_research as cr
import db_manager


def test_parse_iso8601_duration():
    assert cr.parse_iso8601_duration("PT15S") == 15
    assert cr.parse_iso8601_duration("PT1M30S") == 90
    assert cr.parse_iso8601_duration("PT1H2M3S") == 3723
    assert cr.parse_iso8601_duration("PT0S") == 0
    assert cr.parse_iso8601_duration("") == 0


def test_compute_view_velocity_views_per_hour():
    now = datetime.datetime(2026, 1, 2, 0, 0, 0, tzinfo=datetime.timezone.utc)
    published = "2026-01-01T00:00:00Z"  # exactly 24h earlier
    # 24000 views over 24h = 1000 views/hour
    assert cr.compute_view_velocity(24000, published, now=now) == 1000.0


def test_compute_view_velocity_floors_age_to_avoid_divide_by_zero():
    now = datetime.datetime(2026, 1, 1, 0, 0, 30, tzinfo=datetime.timezone.utc)
    published = "2026-01-01T00:00:00Z"  # 30 seconds old
    # Age floored to >= a minimum so a brand-new video doesn't report infinite velocity.
    v = cr.compute_view_velocity(100, published, now=now)
    assert v > 0
    assert v != float("inf")


# --- Fake YouTube Data API (search + videos) ---
class _FakeReq:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return self._data


class _FakeSearch:
    def __init__(self, ids):
        self._ids = ids

    def list(self, **kwargs):
        return _FakeReq({"items": [{"id": {"videoId": v}} for v in self._ids]})


class _FakeVideos:
    def __init__(self, table):
        self._table = table

    def list(self, part, id):
        items = [self._table[v] for v in id.split(",") if v in self._table]
        return _FakeReq({"items": items})


class _FakeDataService:
    def __init__(self, ids, table):
        self._ids = ids
        self._table = table

    def search(self):
        return _FakeSearch(self._ids)

    def videos(self):
        return _FakeVideos(self._table)


def _vid(vid, title, views, published_at, duration, channel="Chan"):
    return {
        "id": vid,
        "snippet": {"title": title, "publishedAt": published_at, "channelTitle": channel},
        "statistics": {"viewCount": str(views)},
        "contentDetails": {"duration": duration},
    }


def test_fetch_competitor_videos_ranks_by_velocity():
    now = datetime.datetime(2026, 1, 11, 0, 0, 0, tzinfo=datetime.timezone.utc)
    table = {
        # 10 days old, 1M views -> ~4167/hr
        "slow": _vid("slow", "Old Hit", 1_000_000, "2026-01-01T00:00:00Z", "PT45S"),
        # 1 day old, 500k views -> ~20833/hr (hotter despite fewer views)
        "fast": _vid("fast", "Fresh Banger", 500_000, "2026-01-10T00:00:00Z", "PT20S"),
    }
    svc = _FakeDataService(["slow", "fast"], table)

    results = cr.fetch_competitor_videos("space facts", service_factory=lambda: svc, now=now)

    assert results[0]["external_id"] == "fast"
    assert results[0]["velocity"] > results[1]["velocity"]
    assert results[0]["duration_seconds"] == 20
    assert results[0]["title"] == "Fresh Banger"


def test_fetch_competitor_videos_empty_query_returns_empty():
    svc = _FakeDataService([], {})
    assert cr.fetch_competitor_videos("nothing", service_factory=lambda: svc) == []


def test_db_competitor_videos_upsert_and_top_velocity():
    q = f"niche_{uuid.uuid4().hex[:6]}"
    db_manager.upsert_competitor_video(q, "lowv", "Low", "ChA", 1000, "2026-01-01T00:00:00Z", 40, 100.0)
    db_manager.upsert_competitor_video(q, "highv", "High", "ChB", 2000, "2026-01-05T00:00:00Z", 22, 5000.0)
    # Upsert again updates velocity in place (no duplicate row).
    db_manager.upsert_competitor_video(q, "highv", "High", "ChB", 9000, "2026-01-05T00:00:00Z", 22, 9999.0)

    top = db_manager.get_top_velocity(q, limit=10)
    assert [r["external_id"] for r in top] == ["highv", "lowv"]
    assert top[0]["velocity"] == 9999.0
    assert top[0]["duration_seconds"] == 22


def test_store_competitor_videos_persists_fetch_results():
    now = datetime.datetime(2026, 1, 11, 0, 0, 0, tzinfo=datetime.timezone.utc)
    q = f"niche_{uuid.uuid4().hex[:6]}"
    table = {"fast": _vid("fast", "Fresh Banger", 500_000, "2026-01-10T00:00:00Z", "PT20S")}
    svc = _FakeDataService(["fast"], table)

    stored = cr.store_competitor_videos(q, service_factory=lambda: svc, now=now)

    assert stored >= 1
    top = db_manager.get_top_velocity(q, limit=5)
    assert top[0]["external_id"] == "fast"


def test_get_competitor_hint_summarizes_winning_patterns():
    q = f"niche_{uuid.uuid4().hex[:6]}"
    db_manager.upsert_competitor_video(q, "a", "Insane Space Fact", "ChA", 800_000, "2026-01-10T00:00:00Z", 22, 18000.0)
    db_manager.upsert_competitor_video(q, "b", "You Won't Believe This", "ChB", 400_000, "2026-01-09T00:00:00Z", 28, 9000.0)

    hint = cr.get_competitor_hint(q, limit=5)

    assert "Insane Space Fact" in hint          # surfaces the hottest title
    assert "/hr" in hint or "per hour" in hint   # mentions the velocity signal
    assert "sec" in hint.lower()                 # mentions winning duration guidance


def test_get_competitor_hint_empty_when_no_data():
    assert cr.get_competitor_hint(f"empty_{uuid.uuid4().hex[:6]}") == ""
