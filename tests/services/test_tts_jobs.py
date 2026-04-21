"""Tests for shared TTS job manager wiring."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace


def _reload_tts_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path / "tts-cache"))
    sys.modules.pop("app.services.tts_jobs", None)
    import app.services.tts_jobs as tts_jobs_module

    return importlib.reload(tts_jobs_module)


def test_tts_job_manager_uses_injected_text_formatter(tmp_path, monkeypatch):
    tts_jobs = _reload_tts_jobs(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    monkeypatch.setattr(tts_jobs.uuid, "uuid4", lambda: SimpleNamespace(hex="abc123"))
    monkeypatch.setattr(tts_jobs.time, "time", lambda: 123.0)
    monkeypatch.setattr(tts_jobs.TtsJobManager, "_prune", lambda self, now: None)
    monkeypatch.setattr(
        tts_jobs.TtsJobManager,
        "_write_meta",
        lambda self, job_id, meta: captured.update(meta=(job_id, meta)),
    )

    class DummyThread:
        def __init__(self, *, target, args, daemon):
            captured["thread"] = {"target": target, "args": args, "daemon": daemon}

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(tts_jobs.threading, "Thread", DummyThread)

    formatter_calls = []

    def formatter(text: str | None, language: str):
        formatter_calls.append((text, language))
        return f"formatted::{text}::{language}"

    manager = tts_jobs.TtsJobManager(
        character="demo",
        replacement="jti",
        text_formatter=formatter,
    )

    job_id = manager.create_job(text="hello", language="zh")

    assert job_id == "tts_abc123"
    assert formatter_calls == [("hello", "zh")]
    assert captured["thread"] == {
        "target": manager._generate_job,
        "args": ("tts_abc123", "formatted::hello::zh", "demo"),
        "daemon": True,
    }
    assert captured["started"] is True


def test_tts_job_manager_singletons_bind_app_specific_formatters(tmp_path, monkeypatch):
    tts_jobs = _reload_tts_jobs(tmp_path, monkeypatch)

    assert tts_jobs.jti_tts_job_manager.text_formatter is tts_jobs.to_jti_tts_text
    assert tts_jobs.hciot_tts_job_manager.text_formatter is tts_jobs.to_hciot_tts_text
