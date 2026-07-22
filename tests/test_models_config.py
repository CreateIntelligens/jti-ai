from types import SimpleNamespace

import pytest

from app import models_config
from app.services import model_discovery


@pytest.mark.parametrize(
    ("model_name", "expected_budget"),
    (
        ("gemini-flash-lite-latest", None),
        ("gemini-3.5-flash-lite", None),
        ("gemini-3.1-flash-lite", None),
        ("gemini-future-alias", None),
        ("gemini-2.5-flash", 0),
        ("gemini-2.5-flash-lite", 0),
        ("models/gemini-2.5-flash-lite-preview-06-17", 0),
    ),
)
def test_thinking_config_matches_model_capability(model_name, expected_budget):
    config = models_config.thinking_config_for_model(model_name)

    if expected_budget is None:
        assert config is None
        return

    assert config is not None
    assert config.thinking_budget == expected_budget


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
