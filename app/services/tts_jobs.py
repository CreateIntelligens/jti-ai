"""Shared background TTS job manager (file-based for multi-worker support)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TTS_API_URL = os.getenv("TTS_API_URL", "http://10.9.0.35:8001/tts")
_TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT_SECONDS", "20"))
_CACHE_TTL_SECONDS = int(os.getenv("TTS_CACHE_TTL_SECONDS", "900"))
_MAX_JOBS = int(os.getenv("TTS_MAX_JOBS", "500"))
_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "/app/data/tts_cache"))


class TtsJobManager:
    """Manage TTS jobs on shared filesystem for multi-worker support."""

    def __init__(
        self,
        character: str,
        api_replacement: str = "",
    ) -> None:
        self.character = character
        self.api_replacement = api_replacement
        self.tts_api_url = _TTS_API_URL
        self.timeout_seconds = _TIMEOUT_SECONDS
        self.cache_ttl_seconds = _CACHE_TTL_SECONDS
        self.max_jobs = _MAX_JOBS
        self.cache_dir = _CACHE_DIR

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, job_id: str) -> Path:
        return self.cache_dir / f"{job_id}.json"

    def _audio_path(self, job_id: str) -> Path:
        return self.cache_dir / f"{job_id}.audio"

    def _read_meta(self, job_id: str) -> dict[str, Any] | None:
        path = self._meta_path(job_id)
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write_meta(self, job_id: str, meta: dict[str, Any]) -> None:
        path = self._meta_path(job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta))
        tmp.rename(path)

    def _remove_job_files(self, job_id: str) -> None:
        for path in (self._meta_path(job_id), self._audio_path(job_id)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def create_job(self, *, text: str, language: str, character: str | None = None) -> str:
        raw_text = (text or "").strip()
        if not raw_text:
            raise ValueError("TTS text is empty")

        effective_character = character or self.character
        prepared_text = raw_text
        job_id = f"tts_{uuid.uuid4().hex}"
        now = time.time()

        self._prune(now)
        self._write_meta(job_id, {
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "content_type": None,
            "error": None,
        })
        logger.info("[TTS] queued job=%s character=%s lang=%s chars=%d", job_id, effective_character, language, len(prepared_text))

        worker = threading.Thread(
            target=self._generate_job,
            args=(job_id, prepared_text, effective_character),
            daemon=True,
        )
        worker.start()
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self._prune(time.time())
        meta = self._read_meta(job_id)
        if not meta:
            return None

        result = dict(meta)
        if meta.get("status") == "ready":
            audio_path = self._audio_path(job_id)
            try:
                result["audio_bytes"] = audio_path.read_bytes()
            except FileNotFoundError:
                result["status"] = "failed"
                result["error"] = "Audio file missing"
                result["audio_bytes"] = None
        else:
            result["audio_bytes"] = None

        return result

    def _set_job_failed(self, job_id: str, error: str) -> None:
        meta = self._read_meta(job_id)
        if not meta:
            return
        now = time.time()
        created_at = float(meta.get("created_at", now))
        meta["status"] = "failed"
        meta["error"] = error
        meta["updated_at"] = now
        self._write_meta(job_id, meta)
        logger.warning("[TTS] failed job=%s elapsed_ms=%.0f error=%s", job_id, (now - created_at) * 1000, error)

    def _set_job_ready(self, job_id: str, audio_bytes: bytes, content_type: str) -> None:
        meta = self._read_meta(job_id)
        if not meta:
            return
        now = time.time()
        created_at = float(meta.get("created_at", now))

        # Write audio file first
        audio_path = self._audio_path(job_id)
        tmp = audio_path.with_suffix(".tmp")
        tmp.write_bytes(audio_bytes)
        tmp.rename(audio_path)

        meta["status"] = "ready"
        meta["content_type"] = content_type
        meta["updated_at"] = now
        self._write_meta(job_id, meta)
        logger.info("[TTS] ready job=%s elapsed_ms=%.0f bytes=%d content_type=%s", job_id, (now - created_at) * 1000, len(audio_bytes), content_type)

    def _generate_job(self, job_id: str, text: str, character: str | None = None) -> None:
        body = {"text": text, "character": character or self.character}
        if self.api_replacement:
            body["replacement"] = self.api_replacement

        request = urllib.request.Request(
            self.tts_api_url,
            data=json.dumps(body).encode("utf-8"),
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

    def _prune(self, now: float) -> None:
        try:
            meta_files = sorted(self.cache_dir.glob("*.json"))
        except OSError:
            return

        live_jobs: list[tuple[str, float]] = []
        for meta_path in meta_files:
            job_id = meta_path.stem
            try:
                meta = json.loads(meta_path.read_text())
                updated_at = float(meta.get("updated_at", meta.get("created_at", now)))
                if now - updated_at > self.cache_ttl_seconds:
                    self._remove_job_files(job_id)
                else:
                    live_jobs.append((job_id, updated_at))
            except (json.JSONDecodeError, OSError, ValueError):
                self._remove_job_files(job_id)

        if len(live_jobs) > self.max_jobs:
            live_jobs.sort(key=lambda x: x[1])
            for job_id, _ in live_jobs[: len(live_jobs) - self.max_jobs]:
                self._remove_job_files(job_id)
