"""Approval-gate behavior at the persistence layer.

The HTTP handlers in backend.py are thin wrappers over these transitions
(approve -> 'scheduled', reject -> 'rejected'); the substance lives here.
"""
import uuid

import db_manager


def _new_generation():
    gid = str(uuid.uuid4())
    db_manager.create_video_generation(gid, "prompt", "Some Topic", None, None, status="completed")
    return gid


def test_pending_job_appears_in_pending_list():
    gid = _new_generation()
    job_id = str(uuid.uuid4())
    db_manager.create_upload_job(
        job_id, gid, ["youtube"], {"title": "T"}, None, status="pending_approval"
    )

    pending_ids = [j["id"] for j in db_manager.get_upload_jobs_by_status("pending_approval")]
    assert job_id in pending_ids


def test_approve_moves_job_to_scheduled():
    gid = _new_generation()
    job_id = str(uuid.uuid4())
    db_manager.create_upload_job(job_id, gid, ["youtube"], {"title": "T"}, None, status="pending_approval")

    db_manager.update_upload_job(job_id, status="scheduled")

    assert db_manager.get_upload_job(job_id)["status"] == "scheduled"
    pending_ids = [j["id"] for j in db_manager.get_upload_jobs_by_status("pending_approval")]
    assert job_id not in pending_ids


def test_reject_marks_job_rejected_and_excludes_from_scheduling():
    gid = _new_generation()
    job_id = str(uuid.uuid4())
    db_manager.create_upload_job(job_id, gid, ["youtube"], {"title": "T"}, None, status="pending_approval")

    db_manager.update_upload_job(job_id, status="rejected")

    assert db_manager.get_upload_job(job_id)["status"] == "rejected"
    # Rejected jobs must never be picked up by the upload scheduler.
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    scheduled_ids = [j["id"] for j in db_manager.get_pending_scheduled_jobs(now)]
    assert job_id not in scheduled_ids
