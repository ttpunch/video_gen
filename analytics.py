"""Analytics feedback loop.

Pulls post-publish performance for videos this app uploaded and stores it, so the
autonomous agent can bias topic selection toward what actually performed instead
of picking blind from raw trends.

Currently covers YouTube (reusing the existing upload OAuth credentials).
Statistics are available for public videos; videos uploaded as ``private`` will
report zeros until made public.
"""
import datetime

import db_manager


# YouTube Analytics API metric name -> our video_stats column name.
_ANALYTICS_METRIC_MAP = {
    "views": "views",
    "averageViewPercentage": "avg_view_pct",
    "averageViewDuration": "avg_view_duration",
    "estimatedMinutesWatched": "estimated_minutes_watched",
    "shares": "shares",
    "subscribersGained": "subscribers_gained",
}


def fetch_youtube_analytics(video_ids, service_factory=None, start_date="2005-01-01", end_date=None):
    """Return ``{video_id: {avg_view_pct, avg_view_duration, ...}}`` of retention
    metrics from the YouTube Analytics API for up to 200 video ids.

    These are the signals that actually predict Shorts virality (how much of the
    video people watch), unlike the public view/like counts in fetch_youtube_stats.
    """
    if not video_ids:
        return {}
    if service_factory is None:
        from uploader_youtube import get_youtube_analytics_service  # lazy: avoids google import at module load
        service_factory = get_youtube_analytics_service
    if end_date is None:
        end_date = datetime.date.today().isoformat()

    service = service_factory()
    resp = service.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        dimensions="video",
        metrics=",".join(m for m in _ANALYTICS_METRIC_MAP if m != "video"),
        filters="video==" + ",".join(video_ids),
        maxResults=200,
    ).execute()

    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    out = {}
    for row in resp.get("rows", []):
        record = dict(zip(headers, row))
        vid = record.get("video")
        if not vid:
            continue
        out[vid] = {
            our: record[api]
            for api, our in _ANALYTICS_METRIC_MAP.items()
            if api in record
        }
    return out


def fetch_youtube_stats(video_ids, service_factory=None):
    """Return ``{video_id: {title, views, likes, comments}}`` for up to 50 ids."""
    if not video_ids:
        return {}
    if service_factory is None:
        from uploader_youtube import get_youtube_service  # lazy: avoids google import at module load
        service_factory = get_youtube_service

    service = service_factory()
    resp = service.videos().list(part="statistics,snippet", id=",".join(video_ids)).execute()

    stats = {}
    for item in resp.get("items", []):
        s = item.get("statistics", {})
        stats[item["id"]] = {
            "title": item.get("snippet", {}).get("title", ""),
            "views": int(s.get("viewCount", 0) or 0),
            "likes": int(s.get("likeCount", 0) or 0),
            "comments": int(s.get("commentCount", 0) or 0),
        }
    return stats


def refresh_youtube_stats(service_factory=None):
    """Refresh stored stats for every YouTube video this app has published."""
    uploads = db_manager.list_platform_uploads("youtube")
    by_external = {u["external_id"]: u for u in uploads if u.get("external_id")}
    ids = list(by_external.keys())
    if not ids:
        return {"updated": 0}

    all_stats = {}
    for i in range(0, len(ids), 50):
        all_stats.update(fetch_youtube_stats(ids[i:i + 50], service_factory=service_factory))

    updated = 0
    for ext_id, stat in all_stats.items():
        upload = by_external.get(ext_id)
        if not upload:
            continue
        db_manager.upsert_video_stat(
            upload["video_generation_id"], "youtube", ext_id,
            stat["views"], stat["likes"], stat["comments"],
        )
        updated += 1
    return {"updated": updated}


def refresh_youtube_analytics(service_factory=None):
    """Refresh stored retention analytics for every YouTube video this app published."""
    uploads = db_manager.list_platform_uploads("youtube")
    by_external = {u["external_id"]: u for u in uploads if u.get("external_id")}
    ids = list(by_external.keys())
    if not ids:
        return {"updated": 0}

    all_metrics = {}
    for i in range(0, len(ids), 200):
        all_metrics.update(fetch_youtube_analytics(ids[i:i + 200], service_factory=service_factory))

    updated = 0
    for ext_id, metrics in all_metrics.items():
        upload = by_external.get(ext_id)
        if not upload or not metrics:
            continue
        db_manager.upsert_video_analytics(upload["video_generation_id"], "youtube", ext_id, metrics)
        updated += 1
    return {"updated": updated}


def get_performance_hint(limit=5):
    """A short natural-language summary of what performed, to ground topic picking.

    Combines reach (views) with the stronger virality signal — audience
    retention — and turns it into concrete, actionable guidance for the LLM.
    """
    top = db_manager.get_top_performing(limit=limit, platform="youtube")
    lines = [f"- \"{t['topic']}\" ({t['views']} views)" for t in top if t.get("topic")]
    if not lines:
        return ""

    hint = (
        "For reference, your best-performing past videos by reach were:\n"
        + "\n".join(lines)
    )

    leaders = db_manager.get_engagement_leaders(limit=limit, platform="youtube")
    retention_lines = [
        f"- \"{l['topic']}\" — {l['avg_view_pct']:.0f}% average view"
        for l in leaders if l.get("topic") and l.get("avg_view_pct") is not None
    ]
    if retention_lines:
        avg_ret = sum(l["avg_view_pct"] for l in leaders if l.get("avg_view_pct") is not None) / len(retention_lines)
        hint += (
            "\n\nYour highest audience-retention videos (how much people actually watched — "
            "the strongest predictor of going viral on Shorts):\n"
            + "\n".join(retention_lines)
            + f"\n\nViewers currently watch ~{avg_ret:.0f}% on average. To boost retention: "
            "front-load the payoff in the first 1-2 seconds, cut slow intros, and keep the hook "
            "visual. Favor angles like the high-retention topics above."
        )
    else:
        hint += "\nFavor topics with a similar angle or theme when it fits the trends."

    return hint
