"""Background TTS job manager for JTI chat."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

from app.services.jti.tts_text import to_tts_text


class JtiTtsJobManager:
    """Manage in-memory TTS jobs and generate audio in background threads."""

    def __init__(self) -> None:
        self.tts_api_url = os.getenv("JTI_TTS_API_URL", "http://10.9.0.35:8001/tts")
        self.default_character = os.getenv("JTI_TTS_CHARACTER", "hayley")
        self.timeout_seconds = float(os.getenv("JTI_TTS_TIMEOUT_SECONDS", "20"))
        self.cache_ttl_seconds = int(os.getenv("JTI_TTS_CACHE_TTL_SECONDS", "900"))
        self.max_jobs = int(os.getenv("JTI_TTS_MAX_JOBS", "500"))

        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(
        self,
        *,
        text: str,
        language: str,
        character: Optional[str] = None,
    ) -> str:
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

        worker = threading.Thread(
            target=self._generate_job,
            args=(job_id, prepared_text, (character or self.default_character).strip() or self.default_character),
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

    def _generate_job(self, job_id: str, text: str, character: str) -> None:
        payload = json.dumps({"text": text, "character": character}).encode("utf-8")
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
        # TTL prune
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if now - float(job.get("updated_at", job.get("created_at", now))) > self.cache_ttl_seconds
        ]
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)

        # Size prune (keep pending jobs; trim old completed/failed first)
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


tts_job_manager = JtiTtsJobManager()
