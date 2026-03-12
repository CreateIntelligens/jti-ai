"""Shared background TTS job manager."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

from app.services.jti.tts_text import to_tts_text

logger = logging.getLogger(__name__)

_TTS_API_URL = os.getenv("TTS_API_URL", "http://10.9.0.35:8001/tts")
_TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT_SECONDS", "20"))
_CACHE_TTL_SECONDS = int(os.getenv("TTS_CACHE_TTL_SECONDS", "900"))
_MAX_JOBS = int(os.getenv("TTS_MAX_JOBS", "500"))


class TtsJobManager:
    """Manage in-memory TTS jobs and generate audio in background threads."""

    def __init__(self, character: str) -> None:
        self.character = character
        self.tts_api_url = _TTS_API_URL
        self.timeout_seconds = _TIMEOUT_SECONDS
        self.cache_ttl_seconds = _CACHE_TTL_SECONDS
        self.max_jobs = _MAX_JOBS

        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self, *, text: str, language: str) -> str:
        raw_text = (text or "").strip()
        if not raw_text:
            raise ValueError("TTS text is empty")

        prepared_text = to_tts_text(raw_text, language) or raw_text
        job_id = f"tts_{uuid.uuid4().hex}"
        now = time.time()

        with self._lock:
            self._prune_locked(now)
            self._jobs[job_id] = {
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "content_type": None,
                "audio_bytes": None,
                "error": None,
            }
        logger.info("[TTS] queued job=%s character=%s lang=%s chars=%d", job_id, self.character, language, len(prepared_text))

        worker = threading.Thread(
            target=self._generate_job,
            args=(job_id, prepared_text),
            daemon=True,
        )
        worker.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            job = self._jobs.get(job_id)
            if not job:
                return None
            return dict(job)

    def _set_job_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            now = time.time()
            job["status"] = "failed"
            job["error"] = error
            job["updated_at"] = now
            created_at = float(job.get("created_at", now))
        logger.warning("[TTS] failed job=%s elapsed_ms=%.0f error=%s", job_id, (now - created_at) * 1000, error)

    def _set_job_ready(self, job_id: str, audio_bytes: bytes, content_type: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            now = time.time()
            job["status"] = "ready"
            job["audio_bytes"] = audio_bytes
            job["content_type"] = content_type
            job["updated_at"] = now
            created_at = float(job.get("created_at", now))
        logger.info("[TTS] ready job=%s elapsed_ms=%.0f bytes=%d content_type=%s", job_id, (now - created_at) * 1000, len(audio_bytes), content_type)

    def _generate_job(self, job_id: str, text: str) -> None:
        payload = json.dumps({"text": text, "character": self.character}).encode("utf-8")
        request = urllib.request.Request(
            self.tts_api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                audio_bytes = response.read()
                content_type = (
                    response.headers.get("Content-Type", "audio/mpeg").split(";")[0].strip()
                ) or "audio/mpeg"

            if not audio_bytes:
                self._set_job_failed(job_id, "TTS API returned empty audio")
                return

            self._set_job_ready(job_id, audio_bytes, content_type)
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            detail = f"TTS API HTTP {exc.code}"
            if body:
                detail = f"{detail}: {body[:300]}"
            self._set_job_failed(job_id, detail)
        except Exception as exc:
            self._set_job_failed(job_id, f"TTS generation failed: {exc}")

    def _prune_locked(self, now: float) -> None:
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if now - float(job.get("updated_at", job.get("created_at", now))) > self.cache_ttl_seconds
        ]
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)

        if len(self._jobs) <= self.max_jobs:
            return

        candidates = [
            (job_id, job)
            for job_id, job in self._jobs.items()
            if job.get("status") in ("ready", "failed")
        ]
        candidates.sort(key=lambda item: float(item[1].get("updated_at", 0)))

        overflow = len(self._jobs) - self.max_jobs
        for job_id, _ in candidates[:overflow]:
            self._jobs.pop(job_id, None)


# Per-app singletons with fixed characters
jti_tts_job_manager = TtsJobManager(character="hayley")
hciot_tts_job_manager = TtsJobManager(character="healthy")
