import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "video_studio.db"))

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
