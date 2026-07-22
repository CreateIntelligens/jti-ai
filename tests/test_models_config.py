from types import SimpleNamespace

from app import models_config
from app.services import model_discovery


def test_fallback_chain_prioritizes_supported_models(monkeypatch):
    discovered = [
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-pro-latest",
    ]
    monkeypatch.setattr(
        model_discovery,
        "get_available_models",
        lambda _client: [SimpleNamespace(name=name) for name in discovered],
    )

    assert models_config.fallback_chain("gemini-flash-lite-latest", object()) == (
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-pro-latest",
    )


def test_fallback_chain_uses_static_priority_when_discovery_is_empty(monkeypatch):
    monkeypatch.setattr(model_discovery, "get_available_models", lambda _client: [])

    assert models_config.fallback_chain("gemini-flash-lite-latest", object()) == (
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    )
