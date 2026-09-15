"""Small durable queue for the single-process local studio.

Requests are committed before returning HTTP success. Queued work survives a
restart; interrupted work is surfaced for explicit retry, never silently replayed
against a paid provider or publishing API. One worker limits GPU/FFmpeg pressure.
"""
import json
import threading
import uuid
from contextlib import contextmanager

import db_manager

_worker_lock = threading.Lock()
_draining = False


class JobConflict(ValueError):
    pass


def initialize():
    with db_manager.get_db_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS work_jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, resource_id TEXT NOT NULL,
            payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
            error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS work_jobs_active
            ON work_jobs(resource_id) WHERE status IN ('queued', 'running')""")
    conn.close()


def enqueue(kind, resource_id, payload, initial_status="queued"):
    import sqlite3
    job_id = uuid.uuid4().hex
    conn = db_manager.get_db_connection()
    try:
        with conn:
            conn.execute("INSERT INTO work_jobs (id, kind, resource_id, payload, status) VALUES (?, ?, ?, ?, ?)",
                         (job_id, kind, resource_id, json.dumps(payload), initial_status))
            if kind == "render":
                conn.execute("UPDATE video_generations SET status = 'rendering', error_message = '', logs = ? WHERE id = ?",
                             (json.dumps(["Render queued."]), resource_id))
    except sqlite3.IntegrityError as exc:
        raise JobConflict("This generation already has queued or running work.") from exc
    finally:
        conn.close()
    return job_id


@contextmanager
def resource_guard(resource_id):
    """Exclude edits/deletion while this generation is being processed."""
    job_id = enqueue("asset", resource_id, {}, initial_status="running")
    try:
        yield
    finally:
        with db_manager.get_db_connection() as conn:
            conn.execute("UPDATE work_jobs SET status = 'completed' WHERE id = ?", (job_id,))
        conn.close()


def active(resource_id):
    conn = db_manager.get_db_connection()
    try:
        return conn.execute("SELECT 1 FROM work_jobs WHERE resource_id = ? AND status IN ('queued', 'running')",
                            (resource_id,)).fetchone() is not None
    finally:
        conn.close()


def recover_interrupted():
    message = "The backend restarted during this job. Review saved progress before retrying."
    with db_manager.get_db_connection() as conn:
        conn.execute("UPDATE work_jobs SET status = 'interrupted', error = ? WHERE status = 'running'", (message,))
        # Also reconcile jobs created by older versions that had no durable queue.
        conn.execute("""UPDATE video_generations SET status = 'failed', error_message = ?
            WHERE status IN ('drafting', 'rendering') AND id NOT IN
            (SELECT resource_id FROM work_jobs WHERE status = 'queued')""", (message,))
        conn.execute("""UPDATE upload_jobs SET status = 'failed', logs = ?
            WHERE status IN ('running', 'queued') AND id NOT IN
            (SELECT json_extract(payload, '$.job_id') FROM work_jobs WHERE kind = 'upload' AND status = 'queued')""",
            (json.dumps([message, "Check YouTube before retrying an interrupted upload."]),))
    conn.close()


def drain(handlers):
    global _draining
    # Only the active worker waits for provider/FFmpeg calls. Other submissions
    # return immediately, preserving the API thread pool for status requests.
    with _worker_lock:
        if _draining:
            return
        _draining = True
    try:
        while True:
            conn = db_manager.get_db_connection()
            try:
                # Coordinate the empty-queue transition with new drain calls;
                # otherwise a submission at shutdown could miss its wakeup.
                with _worker_lock, conn:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute("SELECT * FROM work_jobs WHERE status = 'queued' ORDER BY rowid LIMIT 1").fetchone()
                    if row is None:
                        _draining = False
                        return
                    conn.execute("UPDATE work_jobs SET status = 'running' WHERE id = ?", (row["id"],))
                try:
                    handlers[row["kind"]](json.loads(row["payload"]))
                except Exception as exc:
                    with conn:
                        conn.execute("UPDATE work_jobs SET status = 'failed', error = ? WHERE id = ?", (str(exc), row["id"]))
                    if row["kind"] != "upload":
                        db_manager.update_video_generation(row["resource_id"], status="failed", error_message=str(exc))
                else:
                    with conn:
                        conn.execute("UPDATE work_jobs SET status = 'completed' WHERE id = ?", (row["id"],))
            finally:
                conn.close()
    except BaseException:
        with _worker_lock:
            _draining = False
        raise


initialize()
