import logging

from app.services import app_key_map


def test_load_app_key_map_parses_multiple_groups(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", "jti:JTI傑太日煙,hciot:HCIOT護聯")

    assert app_key_map.load_app_key_map() == {
        "jti": "JTI傑太日煙",
        "hciot": "HCIOT護聯",
    }


def test_load_app_key_map_skips_invalid_entries(monkeypatch, caplog):
    monkeypatch.setenv("APP_KEY_MAP", "bad,jti:, :missing-app,hciot:HCIOT護聯")
    caplog.set_level(logging.WARNING, logger="app.services.app_key_map")

    assert app_key_map.load_app_key_map() == {"hciot": "HCIOT護聯"}
    assert "Invalid APP_KEY_MAP entry" in caplog.text


def test_load_app_key_map_normalizes_app_names(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", " JTI : JTI傑太日煙 , HCIOT : HCIOT護聯 ")

    assert app_key_map.load_app_key_map() == {
        "jti": "JTI傑太日煙",
        "hciot": "HCIOT護聯",
    }


def test_resolve_key_index_for_app_returns_minus_one_when_app_missing(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", "jti:JTI傑太日煙")
    monkeypatch.setattr(app_key_map.gemini_clients, "resolve_key_index_by_name", lambda name: 2)

    assert app_key_map.resolve_key_index_for_app("hciot") == -1


def test_resolve_key_index_for_app_returns_minus_one_when_key_missing(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", "jti:missing")
    monkeypatch.setattr(app_key_map.gemini_clients, "resolve_key_index_by_name", lambda name: -1)

    assert app_key_map.resolve_key_index_for_app("jti") == -1


def test_resolve_key_index_for_app_uses_normalized_app_name(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", "jti:JTI傑太日煙")
    monkeypatch.setattr(app_key_map.gemini_clients, "resolve_key_index_by_name", lambda name: 2)

    assert app_key_map.resolve_key_index_for_app(" JTI ") == 2


def test_validate_app_key_map_logs_missing_key(monkeypatch, caplog):
    monkeypatch.setenv("APP_KEY_MAP", "jti:missing,hciot:HCIOT護聯")
    monkeypatch.setattr(
        app_key_map.gemini_clients,
        "resolve_key_index_by_name",
        lambda name: {"HCIOT護聯": 3}.get(name, -1),
    )
    caplog.set_level(logging.ERROR, logger="app.services.app_key_map")

    assert app_key_map.validate_app_key_map() == [("jti", "missing")]
    assert "jti:missing" in caplog.text


def test_resolve_app_for_key_index(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", "jti:JTI傑太日煙,hciot:HCIOT護聯")
    monkeypatch.setattr(
        app_key_map.gemini_clients,
        "resolve_key_index_by_name",
        lambda name: {"JTI傑太日煙": 1, "HCIOT護聯": 2}.get(name, -1),
    )

    assert app_key_map.resolve_app_for_key_index(1) == "jti"
    assert app_key_map.resolve_app_for_key_index(2) == "hciot"
    assert app_key_map.resolve_app_for_key_index(3) == "general"
    assert app_key_map.resolve_app_for_key_index(-1) == "general"
