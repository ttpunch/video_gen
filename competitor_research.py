"""Competitor view-velocity mining.

Answers "what format / topic is hot in my niche *right now*?" by pulling recent
videos for a query from the YouTube Data API and ranking them by **view
velocity** (views per hour since publish). A 2-day-old video with 500k views is
a far stronger signal than a 2-year-old one with 1M — velocity captures that.

These signals run *before* render cost is spent, so the generator can lean into
formats that are currently working instead of guessing.
"""
import datetime
import re

import db_manager

# A brand-new video with a handful of views shouldn't report near-infinite
# velocity, so we floor its age to this minimum sample window.
_MIN_AGE_HOURS = 1.0

_ISO8601_DURATION = re.compile(
    r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
)


def parse_iso8601_duration(duration):
    """Convert a YouTube ISO-8601 duration like 'PT1M30S' to total seconds."""
    if not duration:
        return 0
    m = _ISO8601_DURATION.fullmatch(duration)
    if not m:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def _parse_published(published_at):
    """Parse a YouTube publishedAt timestamp (RFC 3339, trailing 'Z') to aware UTC."""
    return datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))


def compute_view_velocity(view_count, published_at, now=None):
    """Views per hour since publish, with the age floored to avoid divide-by-zero."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    published = _parse_published(published_at)
    age_hours = (now - published).total_seconds() / 3600.0
    age_hours = max(age_hours, _MIN_AGE_HOURS)
    return round(int(view_count) / age_hours, 2)


def fetch_competitor_videos(query, service_factory=None, max_results=10,
                            published_after=None, now=None):
    """Search YouTube for recent videos matching ``query`` and return them ranked
    by view velocity (hottest first).

    Each item: {external_id, title, channel, views, published_at,
    duration_seconds, velocity}.
    """
    if not query:
        return []
    if service_factory is None:
        from uploader_youtube import get_youtube_service  # lazy: avoids google import at module load
        service_factory = get_youtube_service
    if published_after is None:
        # Only look at the last 30 days so "what's hot now" stays fresh.
        cutoff = (now or datetime.datetime.now(datetime.timezone.utc)) - datetime.timedelta(days=30)
        published_after = cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    service = service_factory()
    search_resp = service.search().list(
        part="snippet", q=query, type="video", order="viewCount",
        publishedAfter=published_after, maxResults=max_results,
    ).execute()

    ids = [it["id"]["videoId"] for it in search_resp.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        return []

    detail_resp = service.videos().list(
        part="statistics,contentDetails,snippet", id=",".join(ids),
    ).execute()

    results = []
    for item in detail_resp.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        published_at = snippet.get("publishedAt", "")
        views = int(stats.get("viewCount", 0) or 0)
        results.append({
            "external_id": item.get("id"),
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "views": views,
            "published_at": published_at,
            "duration_seconds": parse_iso8601_duration(item.get("contentDetails", {}).get("duration", "")),
            "velocity": compute_view_velocity(views, published_at, now=now) if published_at else 0.0,
        })

    results.sort(key=lambda r: r["velocity"], reverse=True)
    return results


def get_competitor_hint(query, limit=5):
    """Natural-language summary of the hottest competitor videos for a query, to
    ground topic/packaging choices in what is currently winning the niche."""
    top = db_manager.get_top_velocity(query, limit=limit)
    top = [t for t in top if t.get("title")]
    if not top:
        return ""

    lines = [
        f"- \"{t['title']}\" ({int(t['velocity']):,}/hr, {t['duration_seconds']}s)"
        for t in top
    ]
    durations = [t["duration_seconds"] for t in top if t.get("duration_seconds")]
    avg_dur = round(sum(durations) / len(durations)) if durations else 0
    return (
        f"Fastest-rising videos in this niche right now (views/hr since publish):\n"
        + "\n".join(lines)
        + (f"\n\nThese winners average ~{avg_dur} seconds. Mirror their hook style, "
           "title pattern and length when it fits — they are what the algorithm is "
           "pushing in this niche today." if avg_dur else "")
    )


def store_competitor_videos(query, service_factory=None, max_results=10, now=None):
    """Fetch and persist competitor videos for ``query``. Returns the count stored."""
    videos = fetch_competitor_videos(query, service_factory=service_factory,
                                     max_results=max_results, now=now)
    for v in videos:
        db_manager.upsert_competitor_video(
            query, v["external_id"], v["title"], v["channel"], v["views"],
            v["published_at"], v["duration_seconds"], v["velocity"],
        )
    return len(videos)
