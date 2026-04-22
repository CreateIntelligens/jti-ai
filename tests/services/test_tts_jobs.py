"""Tests for shared TTS job manager wiring."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace


def _reload_module(module_name: str, tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path / "tts-cache"))
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def _reload_tts_jobs(tmp_path, monkeypatch):
    return _reload_module("app.services.tts_jobs", tmp_path, monkeypatch)


def _assert_manager_binding(manager, tts_jobs, formatter, api_replacement: str, get_manager) -> None:
    assert isinstance(manager, tts_jobs.TtsJobManager)
    assert manager.text_formatter is formatter
    assert manager.api_replacement == api_replacement
    assert get_manager() is manager


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
        api_replacement="jti",
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


def test_app_tts_modules_bind_expected_managers_and_formatters(tmp_path, monkeypatch):
    tts_jobs = _reload_tts_jobs(tmp_path, monkeypatch)
    jti_tts = _reload_module("app.services.jti.tts", tmp_path, monkeypatch)
    hciot_tts = _reload_module("app.services.hciot.tts", tmp_path, monkeypatch)

    jti_manager = jti_tts.get_jti_tts_job_manager()
    _assert_manager_binding(
        jti_manager,
        tts_jobs,
        jti_tts.to_jti_tts_text,
        "jti",
        jti_tts.get_jti_tts_job_manager,
    )

    hciot_manager = hciot_tts.get_hciot_tts_job_manager()
    _assert_manager_binding(
        hciot_manager,
        tts_jobs,
        hciot_tts.to_hciot_tts_text,
        "hciot",
        hciot_tts.get_hciot_tts_job_manager,
    )
