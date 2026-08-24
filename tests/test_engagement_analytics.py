"""Tests for the deeper YouTube engagement/retention analytics loop."""
import uuid

import db_manager
import analytics


# --- Fake YouTube Analytics API v2 service (reports().query().execute()) ---
class _FakeReq:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return self._data


class _FakeReports:
    def __init__(self, data):
        self._data = data
        self.last_kwargs = None

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeReq(self._data)


class _FakeAnalyticsService:
    def __init__(self, data):
        self._reports = _FakeReports(data)

    def reports(self):
        return self._reports


def _seed(topic, ext, views=1000):
    gid = str(uuid.uuid4())
    db_manager.create_video_generation(gid, "p", topic, None, None, status="completed")
    db_manager.record_platform_upload(gid, "youtube", ext)
    db_manager.upsert_video_stat(gid, "youtube", ext, views=views, likes=1, comments=1)
    return gid


def test_upsert_video_analytics_stores_retention_metrics():
    ext = f"yt_{uuid.uuid4().hex[:8]}"
    gid = _seed("Retention Test", ext)

    db_manager.upsert_video_analytics(gid, "youtube", ext, {
        "avg_view_pct": 55.5,
        "avg_view_duration": 12.3,
        "estimated_minutes_watched": 100.0,
        "shares": 4,
        "subscribers_gained": 2,
    })

    conn = db_manager.get_db_connection()
    row = conn.execute(
        "SELECT avg_view_pct, avg_view_duration, shares FROM video_stats WHERE external_id = ?",
        (ext,),
    ).fetchone()
    conn.close()
    assert row["avg_view_pct"] == 55.5
    assert row["avg_view_duration"] == 12.3
    assert row["shares"] == 4


def test_get_engagement_leaders_ranks_by_retention():
    low_ext = f"yt_{uuid.uuid4().hex[:8]}"
    high_ext = f"yt_{uuid.uuid4().hex[:8]}"
    no_analytics_ext = f"yt_{uuid.uuid4().hex[:8]}"
    low_gid = _seed("Low Retention Topic", low_ext, views=5000)
    high_gid = _seed("High Retention Topic", high_ext, views=100)
    _seed("No Analytics Topic", no_analytics_ext, views=999999)

    db_manager.upsert_video_analytics(low_gid, "youtube", low_ext, {"avg_view_pct": 20.0})
    db_manager.upsert_video_analytics(high_gid, "youtube", high_ext, {"avg_view_pct": 70.0})

    leaders = db_manager.get_engagement_leaders(limit=50, platform="youtube")
    topics = [r["topic"] for r in leaders]

    # Ordered by retention (not views), and rows lacking analytics are excluded.
    assert topics.index("High Retention Topic") < topics.index("Low Retention Topic")
    assert "No Analytics Topic" not in topics


def test_fetch_youtube_analytics_parses_report_rows():
    data = {
        "columnHeaders": [
            {"name": "video"},
            {"name": "views"},
            {"name": "averageViewPercentage"},
            {"name": "averageViewDuration"},
            {"name": "estimatedMinutesWatched"},
            {"name": "shares"},
            {"name": "subscribersGained"},
        ],
        "rows": [
            ["vidA", 1000, 62.5, 18.0, 300.0, 7, 3],
            ["vidB", 50, 12.0, 4.0, 3.0, 0, 0],
        ],
    }
    result = analytics.fetch_youtube_analytics(
        ["vidA", "vidB"], service_factory=lambda: _FakeAnalyticsService(data)
    )
    assert result["vidA"]["avg_view_pct"] == 62.5
    assert result["vidA"]["avg_view_duration"] == 18.0
    assert result["vidA"]["estimated_minutes_watched"] == 300.0
    assert result["vidA"]["shares"] == 7
    assert result["vidA"]["subscribers_gained"] == 3
    assert result["vidB"]["avg_view_pct"] == 12.0


def test_fetch_youtube_analytics_empty_input():
    assert analytics.fetch_youtube_analytics([], service_factory=lambda: None) == {}


def test_refresh_youtube_analytics_stores_retention():
    ext = f"yt_{uuid.uuid4().hex[:8]}"
    _seed("Refresh Retention Topic", ext, views=2000)

    data = {
        "columnHeaders": [{"name": "video"}, {"name": "averageViewPercentage"}],
        "rows": [[ext, 48.0]],
    }
    result = analytics.refresh_youtube_analytics(service_factory=lambda: _FakeAnalyticsService(data))

    assert result["updated"] >= 1
    conn = db_manager.get_db_connection()
    row = conn.execute("SELECT avg_view_pct FROM video_stats WHERE external_id = ?", (ext,)).fetchone()
    conn.close()
    assert row["avg_view_pct"] == 48.0


def test_get_performance_hint_includes_retention_signal():
    ext = f"yt_{uuid.uuid4().hex[:8]}"
    gid = _seed("Topic With Great Retention", ext, views=4242)
    db_manager.upsert_video_analytics(gid, "youtube", ext, {"avg_view_pct": 88.0})

    hint = analytics.get_performance_hint(limit=5)

    assert "Topic With Great Retention" in hint
    assert "88%" in hint
    assert "retention" in hint.lower()
