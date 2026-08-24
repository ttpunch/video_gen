import uuid

import db_manager
import analytics


# --- A fake YouTube service so tests never hit the network ---
class _FakeRequest:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return self._data


class _FakeVideos:
    def __init__(self, table):
        self._table = table

    def list(self, part, id):
        ids = id.split(",")
        items = []
        for vid in ids:
            if vid in self._table:
                row = self._table[vid]
                items.append({
                    "id": vid,
                    "statistics": row["stats"],
                    "snippet": {"title": row["title"]},
                })
        return _FakeRequest({"items": items})


class _FakeService:
    def __init__(self, table):
        self._table = table

    def videos(self):
        return _FakeVideos(self._table)


def test_fetch_youtube_stats_parses_response():
    table = {"vid1": {"title": "Hello", "stats": {"viewCount": "100", "likeCount": "5", "commentCount": "2"}}}
    stats = analytics.fetch_youtube_stats(["vid1"], service_factory=lambda: _FakeService(table))
    assert stats["vid1"]["views"] == 100
    assert stats["vid1"]["likes"] == 5
    assert stats["vid1"]["comments"] == 2
    assert stats["vid1"]["title"] == "Hello"


def test_fetch_youtube_stats_empty_input():
    assert analytics.fetch_youtube_stats([], service_factory=lambda: None) == {}


def test_refresh_youtube_stats_stores_metrics():
    gid = str(uuid.uuid4())
    ext = f"yt_{uuid.uuid4().hex[:8]}"
    db_manager.create_video_generation(gid, "p", "Space Facts", None, None, status="completed")
    db_manager.record_platform_upload(gid, "youtube", ext)

    table = {ext: {"title": "Space", "stats": {"viewCount": "9999999", "likeCount": "10", "commentCount": "1"}}}
    result = analytics.refresh_youtube_stats(service_factory=lambda: _FakeService(table))

    assert result["updated"] >= 1
    conn = db_manager.get_db_connection()
    row = conn.execute("SELECT views FROM video_stats WHERE external_id = ?", (ext,)).fetchone()
    conn.close()
    assert row["views"] == 9999999


def test_get_performance_hint_includes_top_topic():
    gid = str(uuid.uuid4())
    ext = f"yt_{uuid.uuid4().hex[:8]}"
    db_manager.create_video_generation(gid, "p", "A Wildly Popular Topic", None, None, status="completed")
    db_manager.upsert_video_stat(gid, "youtube", ext, views=10_000_000, likes=1, comments=1)

    hint = analytics.get_performance_hint(limit=5)
    assert "A Wildly Popular Topic" in hint


def test_get_performance_hint_empty_when_no_stats(monkeypatch):
    monkeypatch.setattr(db_manager, "get_top_performing", lambda limit=5, platform="youtube": [])
    assert analytics.get_performance_hint() == ""
