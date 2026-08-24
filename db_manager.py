import sqlite3
import json
import os
import uuid
from datetime import datetime

# Allow tests / alternate deployments to point at a different database file.
DB_PATH = os.environ.get("VIDEO_STUDIO_DB") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "video_studio.db")
)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create database tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_generations (
        id TEXT PRIMARY KEY,
        prompt TEXT,
        topic TEXT,
        script_data TEXT, -- JSON string
        storyboard TEXT,  -- JSON string
        final_video_path TEXT,
        status TEXT,      -- 'draft', 'rendering', 'completed', 'failed'
        created_at TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS upload_jobs (
        id TEXT PRIMARY KEY,
        video_generation_id TEXT,
        platforms TEXT,         -- JSON array, e.g. ["youtube", "instagram"]
        youtube_metadata TEXT,  -- JSON string
        instagram_metadata TEXT, -- JSON string
        status TEXT,            -- 'scheduled', 'running', 'completed', 'failed'
        scheduled_time TEXT,    -- ISO 8601 timestamp
        logs TEXT,              -- JSON array of strings
        created_at TEXT,
        FOREIGN KEY(video_generation_id) REFERENCES video_generations(id)
    );
    """)
    
    # Ledger of successful per-platform uploads. The UNIQUE constraint makes
    # double-publishing the same generation to the same platform impossible.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS platform_uploads (
        id TEXT PRIMARY KEY,
        video_generation_id TEXT,
        platform TEXT,          -- 'youtube', 'instagram'
        external_id TEXT,       -- platform-side video / media id
        status TEXT,            -- 'completed', 'failed'
        created_at TEXT,
        UNIQUE(video_generation_id, platform)
    );
    """)

    # Per-operation cost ledger (Leonardo image/motion etc.) for the budget guard.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_costs (
        id TEXT PRIMARY KEY,
        video_generation_id TEXT,
        service TEXT,           -- 'leonardo'
        operation TEXT,         -- 'image', 'motion'
        cost REAL,
        created_at TEXT
    );
    """)

    # Post-publish performance metrics, the analytics feedback loop.
    # The avg_view_pct / avg_view_duration / impressions / ctr columns hold the
    # deeper YouTube Analytics retention signals (added later via migration for
    # existing databases — see _migrate_video_stats_columns).
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_stats (
        id TEXT PRIMARY KEY,
        video_generation_id TEXT,
        platform TEXT,
        external_id TEXT,
        views INTEGER,
        likes INTEGER,
        comments INTEGER,
        avg_view_pct REAL,
        avg_view_duration REAL,
        estimated_minutes_watched REAL,
        shares INTEGER,
        subscribers_gained INTEGER,
        impressions INTEGER,
        ctr REAL,
        analytics_fetched_at TEXT,
        fetched_at TEXT,
        UNIQUE(platform, external_id)
    );
    """)

    _migrate_video_stats_columns(cursor)

    # Mined competitor videos for "what format is hot right now" (view-velocity).
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS competitor_videos (
        id TEXT PRIMARY KEY,
        query TEXT,
        external_id TEXT,
        title TEXT,
        channel TEXT,
        views INTEGER,
        published_at TEXT,
        duration_seconds INTEGER,
        velocity REAL,
        fetched_at TEXT,
        UNIQUE(query, external_id)
    );
    """)

    conn.commit()
    conn.close()


# Engagement columns added after the original video_stats schema shipped. For
# existing databases we add any that are missing so older installs upgrade
# cleanly without losing their stored views/likes.
_VIDEO_STATS_ENGAGEMENT_COLUMNS = {
    "avg_view_pct": "REAL",
    "avg_view_duration": "REAL",
    "estimated_minutes_watched": "REAL",
    "shares": "INTEGER",
    "subscribers_gained": "INTEGER",
    "impressions": "INTEGER",
    "ctr": "REAL",
    "analytics_fetched_at": "TEXT",
}


def _migrate_video_stats_columns(cursor):
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(video_stats)").fetchall()}
    for col, col_type in _VIDEO_STATS_ENGAGEMENT_COLUMNS.items():
        if col not in existing:
            cursor.execute(f"ALTER TABLE video_stats ADD COLUMN {col} {col_type}")

# Cost / budget helpers
def record_api_cost(video_generation_id, service, operation, cost):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO api_costs (id, video_generation_id, service, operation, cost, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), video_generation_id, service, operation, float(cost), datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()
    conn.close()

def get_spend_today(service=None):
    """Total recorded cost for today (UTC). Filter by service if given."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cursor = conn.cursor()
    if service:
        cursor.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM api_costs WHERE service = ? AND created_at LIKE ?",
            (service, today + "%"),
        )
    else:
        cursor.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM api_costs WHERE created_at LIKE ?",
            (today + "%",),
        )
    total = cursor.fetchone()[0]
    conn.close()
    return float(total or 0.0)

def get_spend_for_generation(video_generation_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(SUM(cost), 0) FROM api_costs WHERE video_generation_id = ?",
        (video_generation_id,),
    )
    total = cursor.fetchone()[0]
    conn.close()
    return float(total or 0.0)

# Analytics helpers
def upsert_video_stat(video_generation_id, platform, external_id, views, likes, comments):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO video_stats (id, video_generation_id, platform, external_id, views, likes, comments, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform, external_id)
        DO UPDATE SET views = excluded.views,
                      likes = excluded.likes,
                      comments = excluded.comments,
                      fetched_at = excluded.fetched_at
        """,
        (str(uuid.uuid4()), video_generation_id, platform, external_id,
         int(views), int(likes), int(comments), datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()
    conn.close()

def upsert_video_analytics(video_generation_id, platform, external_id, metrics):
    """Store deeper engagement/retention metrics for a published video.

    ``metrics`` is a dict that may contain any of: avg_view_pct,
    avg_view_duration, estimated_minutes_watched, shares, subscribers_gained,
    impressions, ctr. Missing keys are left untouched. Upserts on
    (platform, external_id) so it works whether or not a basic stats row exists.
    """
    allowed = [c for c in _VIDEO_STATS_ENGAGEMENT_COLUMNS if c != "analytics_fetched_at"]
    cols = [c for c in allowed if metrics.get(c) is not None]
    fetched_at = datetime.utcnow().isoformat() + "Z"

    conn = get_db_connection()
    cursor = conn.cursor()
    insert_cols = ["id", "video_generation_id", "platform", "external_id", "analytics_fetched_at"] + cols
    placeholders = ", ".join("?" for _ in insert_cols)
    values = [str(uuid.uuid4()), video_generation_id, platform, external_id, fetched_at] + [metrics[c] for c in cols]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in cols + ["analytics_fetched_at"])
    cursor.execute(
        f"""
        INSERT INTO video_stats ({", ".join(insert_cols)})
        VALUES ({placeholders})
        ON CONFLICT(platform, external_id)
        DO UPDATE SET {set_clause}
        """,
        values,
    )
    conn.commit()
    conn.close()

def list_platform_uploads(platform=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if platform:
        cursor.execute("SELECT * FROM platform_uploads WHERE platform = ?", (platform,))
    else:
        cursor.execute("SELECT * FROM platform_uploads")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_top_performing(limit=5, platform="youtube"):
    """Best-performing published videos by views, joined to their topic."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT vs.external_id, vs.views, vs.likes, vs.comments, vg.topic
        FROM video_stats vs
        LEFT JOIN video_generations vg ON vs.video_generation_id = vg.id
        WHERE vs.platform = ?
        ORDER BY vs.views DESC
        LIMIT ?
        """,
        (platform, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_engagement_leaders(limit=5, platform="youtube"):
    """Published videos ranked by audience retention (avg_view_pct), joined to
    their topic. Only includes videos that actually have retention analytics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT vs.external_id, vs.views, vs.likes, vs.comments,
               vs.avg_view_pct, vs.avg_view_duration, vs.estimated_minutes_watched,
               vs.shares, vs.subscribers_gained, vs.impressions, vs.ctr,
               vg.topic
        FROM video_stats vs
        LEFT JOIN video_generations vg ON vs.video_generation_id = vg.id
        WHERE vs.platform = ? AND vs.avg_view_pct IS NOT NULL
        ORDER BY vs.avg_view_pct DESC
        LIMIT ?
        """,
        (platform, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def upsert_competitor_video(query, external_id, title, channel, views, published_at, duration_seconds, velocity):
    """Store (or refresh) a mined competitor video, keyed by (query, external_id)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO competitor_videos
            (id, query, external_id, title, channel, views, published_at, duration_seconds, velocity, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(query, external_id)
        DO UPDATE SET title = excluded.title,
                      channel = excluded.channel,
                      views = excluded.views,
                      published_at = excluded.published_at,
                      duration_seconds = excluded.duration_seconds,
                      velocity = excluded.velocity,
                      fetched_at = excluded.fetched_at
        """,
        (str(uuid.uuid4()), query, external_id, title, channel, int(views or 0),
         published_at, int(duration_seconds or 0), float(velocity or 0.0),
         datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()
    conn.close()

def get_top_velocity(query, limit=10):
    """Mined competitor videos for a query, hottest (highest velocity) first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT external_id, title, channel, views, published_at, duration_seconds, velocity
        FROM competitor_videos
        WHERE query = ?
        ORDER BY velocity DESC
        LIMIT ?
        """,
        (query, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_upload_jobs_by_status(status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uj.*, vg.topic, vg.final_video_path
        FROM upload_jobs uj
        LEFT JOIN video_generations vg ON uj.video_generation_id = vg.id
        WHERE uj.status = ?
        ORDER BY uj.created_at DESC
    """, (status,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        res = dict(r)
        for k in ("platforms", "youtube_metadata", "instagram_metadata", "logs"):
            if res.get(k):
                res[k] = json.loads(res[k])
        results.append(res)
    return results

# Dedup / idempotency helpers
def get_platform_upload(video_generation_id, platform):
    """Return the upload-ledger row for (generation, platform), or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM platform_uploads WHERE video_generation_id = ? AND platform = ?",
        (video_generation_id, platform),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def is_platform_uploaded(video_generation_id, platform):
    """True if this generation was already successfully published to the platform."""
    row = get_platform_upload(video_generation_id, platform)
    return bool(row and row.get("status") == "completed" and row.get("external_id"))

def record_platform_upload(video_generation_id, platform, external_id, status="completed"):
    """Record (or overwrite) the result of publishing a generation to a platform."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO platform_uploads (id, video_generation_id, platform, external_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_generation_id, platform)
        DO UPDATE SET external_id = excluded.external_id,
                      status = excluded.status,
                      created_at = excluded.created_at
        """,
        (
            str(uuid.uuid4()),
            video_generation_id,
            platform,
            external_id,
            status,
            datetime.utcnow().isoformat() + "Z",
        ),
    )
    conn.commit()
    conn.close()

# Video Generation helpers
def create_video_generation(gen_id, prompt, topic, script_data, storyboard, status="draft"):
    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.utcnow().isoformat() + "Z"
    
    cursor.execute(
        """
        INSERT INTO video_generations (id, prompt, topic, script_data, storyboard, final_video_path, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gen_id,
            prompt,
            topic,
            json.dumps(script_data) if script_data else None,
            json.dumps(storyboard) if storyboard else None,
            None,
            status,
            created_at
        )
    )
    conn.commit()
    conn.close()
    return gen_id

def update_video_generation(gen_id, topic=None, script_data=None, storyboard=None, final_video_path=None, status=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    fields = []
    values = []
    
    if topic is not None:
        fields.append("topic = ?")
        values.append(topic)
    if script_data is not None:
        fields.append("script_data = ?")
        values.append(json.dumps(script_data))
    if storyboard is not None:
        fields.append("storyboard = ?")
        values.append(json.dumps(storyboard))
    if final_video_path is not None:
        fields.append("final_video_path = ?")
        values.append(final_video_path)
    if status is not None:
        fields.append("status = ?")
        values.append(status)
        
    if not fields:
        conn.close()
        return
        
    values.append(gen_id)
    query = f"UPDATE video_generations SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, tuple(values))
    conn.commit()
    conn.close()

def get_video_generation(gen_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_generations WHERE id = ?", (gen_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
        
    res = dict(row)
    if res.get("script_data"):
        res["script_data"] = json.loads(res["script_data"])
    if res.get("storyboard"):
        res["storyboard"] = json.loads(res["storyboard"])
    return res

def get_recent_topics(limit=40):
    """Return the most recently generated topics (newest first) to avoid repeats."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT topic FROM video_generations WHERE topic IS NOT NULL AND topic != '' "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]

def list_video_generations():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_generations ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        res = dict(r)
        if res.get("script_data"):
            res["script_data"] = json.loads(res["script_data"])
        if res.get("storyboard"):
            res["storyboard"] = json.loads(res["storyboard"])
        results.append(res)
    return results

# Upload Job helpers
def create_upload_job(job_id, video_generation_id, platforms, youtube_metadata, instagram_metadata, status="scheduled", scheduled_time=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.utcnow().isoformat() + "Z"
    
    if not scheduled_time:
        scheduled_time = created_at
        
    cursor.execute(
        """
        INSERT INTO upload_jobs (id, video_generation_id, platforms, youtube_metadata, instagram_metadata, status, scheduled_time, logs, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            video_generation_id,
            json.dumps(platforms),
            json.dumps(youtube_metadata) if youtube_metadata else None,
            json.dumps(instagram_metadata) if instagram_metadata else None,
            status,
            scheduled_time,
            json.dumps(["Job queued"]),
            created_at
        )
    )
    conn.commit()
    conn.close()
    return job_id

def update_upload_job(job_id, status=None, logs=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    fields = []
    values = []
    
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if logs is not None:
        fields.append("logs = ?")
        values.append(json.dumps(logs))
        
    if not fields:
        conn.close()
        return
        
    values.append(job_id)
    query = f"UPDATE upload_jobs SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, tuple(values))
    conn.commit()
    conn.close()

def get_upload_job(job_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM upload_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
        
    res = dict(row)
    if res.get("platforms"):
        res["platforms"] = json.loads(res["platforms"])
    if res.get("youtube_metadata"):
        res["youtube_metadata"] = json.loads(res["youtube_metadata"])
    if res.get("instagram_metadata"):
        res["instagram_metadata"] = json.loads(res["instagram_metadata"])
    if res.get("logs"):
        res["logs"] = json.loads(res["logs"])
    return res

def list_upload_jobs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uj.*, vg.topic, vg.final_video_path 
        FROM upload_jobs uj
        LEFT JOIN video_generations vg ON uj.video_generation_id = vg.id
        ORDER BY uj.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        res = dict(r)
        if res.get("platforms"):
            res["platforms"] = json.loads(res["platforms"])
        if res.get("youtube_metadata"):
            res["youtube_metadata"] = json.loads(res["youtube_metadata"])
        if res.get("instagram_metadata"):
            res["instagram_metadata"] = json.loads(res["instagram_metadata"])
        if res.get("logs"):
            res["logs"] = json.loads(res["logs"])
        results.append(res)
    return results

def get_pending_scheduled_jobs(now_iso):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM upload_jobs WHERE status = 'scheduled' AND scheduled_time <= ?",
        (now_iso,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        res = dict(r)
        if res.get("platforms"):
            res["platforms"] = json.loads(res["platforms"])
        if res.get("youtube_metadata"):
            res["youtube_metadata"] = json.loads(res["youtube_metadata"])
        if res.get("instagram_metadata"):
            res["instagram_metadata"] = json.loads(res["instagram_metadata"])
        if res.get("logs"):
            res["logs"] = json.loads(res["logs"])
        results.append(res)
    return results

def delete_video_generation(gen_id):
    """Deletes a video generation from DB and also removes its video file and storyboard assets."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch info before deletion to get file paths
    cursor.execute("SELECT storyboard, final_video_path FROM video_generations WHERE id = ?", (gen_id,))
    row = cursor.fetchone()
    
    if row:
        storyboard_json, final_video_path = row
        
        # A. Collect all timestamps associated with this generation to clean up the temp folder
        timestamps = set()
        import re
        
        def extract_timestamps(path_str):
            if path_str:
                # Find all sequences of 9-10 digits (Unix timestamps)
                for match in re.findall(r'\d{9,10}', os.path.basename(path_str)):
                    timestamps.add(int(match))
        
        extract_timestamps(final_video_path)
        if storyboard_json:
            try:
                storyboard = json.loads(storyboard_json)
                for scene in storyboard:
                    extract_timestamps(scene.get("image_path"))
                    extract_timestamps(scene.get("audio_path"))
            except Exception:
                pass

        # B. Delete final video file
        if final_video_path and os.path.exists(final_video_path):
            try:
                os.remove(final_video_path)
            except Exception as e:
                print(f"Error removing final video file {final_video_path}: {e}")
                
        # C. Delete storyboard asset files (like generated scene images and narration audio clips)
        if storyboard_json:
            try:
                storyboard = json.loads(storyboard_json)
                for scene in storyboard:
                    # Delete scene image
                    img_path = scene.get("image_path")
                    if img_path and os.path.exists(img_path):
                        try:
                            os.remove(img_path)
                        except Exception as e:
                            print(f"Error removing image: {img_path}, error: {e}")
                            
                    # Delete scene voice audio
                    audio_path = scene.get("audio_path")
                    if audio_path and os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                        except Exception as e:
                            print(f"Error removing audio: {audio_path}, error: {e}")
            except Exception as e:
                print(f"Error parsing storyboard during deletion for generation {gen_id}: {e}")

        # D. Scan the temp folder and delete any file whose timestamp is in range of the collected timestamps
        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            # Expand range to capture files generated slightly before or after (within 60 seconds)
            min_range = min_ts - 60
            max_range = max_ts + 60
            
            temp_dir = os.path.abspath("temp")
            if os.path.exists(temp_dir):
                try:
                    for item in os.listdir(temp_dir):
                        item_path = os.path.join(temp_dir, item)
                        if os.path.isfile(item_path):
                            # Extract any 9-10 digit number from the filename
                            matches = re.findall(r'\d{9,10}', item)
                            for match_str in matches:
                                ts_val = int(match_str)
                                if min_range <= ts_val <= max_range:
                                    try:
                                        os.remove(item_path)
                                    except Exception as e:
                                        print(f"Error removing temp file {item_path}: {e}")
                                    break
                except Exception as e:
                    print(f"Error scanning temp directory for cleanup: {e}")
                    
    # 2. Delete dependent upload jobs first
    cursor.execute("DELETE FROM upload_jobs WHERE video_generation_id = ?", (gen_id,))
    
    # 3. Delete the generation row
    cursor.execute("DELETE FROM video_generations WHERE id = ?", (gen_id,))
    conn.commit()
    conn.close()

# Initialize on import
init_db()
