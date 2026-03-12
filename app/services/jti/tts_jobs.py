"""Backwards-compatible shim — use app.services.tts_jobs directly."""

from app.services.tts_jobs import TtsJobManager, jti_tts_job_manager as tts_job_manager

__all__ = ["TtsJobManager", "tts_job_manager"]
