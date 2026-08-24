"""Shared test setup.

Point db_manager at a throwaway SQLite file *before* it is imported anywhere,
so tests never touch the real ``video_studio.db``. This module is imported by
pytest before any test module, so the env var is set in time.
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="video_gen_tests_")
os.environ["VIDEO_STUDIO_DB"] = os.path.join(_TMP_DIR, "test_video_studio.db")
