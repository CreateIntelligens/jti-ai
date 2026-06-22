"""Regression tests for shared managed-app TTS wiring."""

from pathlib import Path

from fastapi import APIRouter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REMOVED_DEPS_WRAPPERS = (
    "get_jti_tts_job_manager",
    "get_hciot_tts_job_manager",
    "get_esg_tts_job_manager",
)


def test_general_managed_tts_config_uses_expected_character() -> None:
    from app.services.general.tts import MANAGED_TTS_CONFIGS

    config = MANAGED_TTS_CONFIGS["general"]

    assert config.app == "general"
    assert config.character_env == "GENERAL_TTS_CHARACTER"
    assert config.default_character == "hayley"


def test_wire_tts_registers_shared_endpoints_and_returns_getter(monkeypatch) -> None:
    from app.routers import tts_utils
    from app.services.tts_text import prepare_tts_text

    router = APIRouter()
    manager = object()
    registered = {}

    def get_manager(app: str):
        registered["app"] = app
        return manager

    def register(router_arg, getter_arg, text_formatter=None):
        registered["router"] = router_arg
        registered["getter"] = getter_arg
        registered["text_formatter"] = text_formatter

    monkeypatch.setattr(
        tts_utils,
        "get_managed_tts_job_manager",
        get_manager,
        raising=False,
    )
    monkeypatch.setattr(tts_utils, "register_tts_endpoints", register)

    getter = tts_utils.wire_tts(router, "general")

    assert registered["router"] is router
    assert registered["getter"] is getter
    assert registered["text_formatter"] is prepare_tts_text
    assert getter() is manager
    assert registered["app"] == "general"


def test_production_code_has_no_removed_tts_dependency_wrappers() -> None:
    offenders: dict[str, list[str]] = {}

    for path in (PROJECT_ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        matches = [symbol for symbol in REMOVED_DEPS_WRAPPERS if symbol in source]
        if matches:
            offenders[str(path.relative_to(PROJECT_ROOT))] = matches

    assert offenders == {}
