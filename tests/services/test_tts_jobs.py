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


def _assert_manager_binding(manager, tts_jobs, api_replacement: str, get_manager) -> None:
    assert isinstance(manager, tts_jobs.TtsJobManager)
    assert manager.api_replacement == api_replacement
    assert get_manager() is manager


def test_tts_job_manager_passes_text_through_unchanged(tmp_path, monkeypatch):
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

    manager = tts_jobs.TtsJobManager(character="demo", api_replacement="jti")

    job_id = manager.create_job(text="hello", language="zh")

    assert job_id == "tts_abc123"
    assert captured["thread"] == {
        "target": manager._generate_job,
        "args": ("tts_abc123", "hello", "demo"),
        "daemon": True,
    }
    assert captured["started"] is True


def test_general_tts_factory_binds_expected_managers(tmp_path, monkeypatch):
    tts_jobs = _reload_tts_jobs(tmp_path, monkeypatch)
    general_tts = _reload_module("app.services.general.tts", tmp_path, monkeypatch)
    monkeypatch.setenv("JTI_TTS_CHARACTER", "hayley,backup")
    monkeypatch.setenv("HCIOT_TTS_CHARACTER", "healthy2,backup")

    def get_jti_manager():
        return general_tts.get_tts_job_manager(
            "jti", "JTI_TTS_CHARACTER", "hayley"
        )

    def get_hciot_manager():
        return general_tts.get_tts_job_manager(
            "hciot", "HCIOT_TTS_CHARACTER", "healthy2"
        )

    _assert_manager_binding(
        get_jti_manager(),
        tts_jobs,
        "jti",
        get_jti_manager,
    )
    assert get_jti_manager().character == "hayley"
    _assert_manager_binding(
        get_hciot_manager(),
        tts_jobs,
        "hciot",
        get_hciot_manager,
    )
    assert get_hciot_manager().character == "healthy2"
