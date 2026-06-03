from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import verify_auth


def _request(
    headers: dict[str, str],
    query_params: dict | None = None,
    cookies: dict | None = None,
):
    return SimpleNamespace(headers=headers, query_params=query_params or {}, cookies=cookies or {})


def test_verify_auth_rejects_same_origin_via_forwarded_host():
    with pytest.raises(HTTPException) as exc_info:
        verify_auth(_request({
            "host": "backend:8914",
            "x-forwarded-host": "10.9.0.32:8914",
            "origin": "http://10.9.0.32:8914",
        }))

    assert exc_info.value.status_code == 401


def test_verify_auth_rejects_browser_fetch_metadata_same_origin():
    with pytest.raises(HTTPException) as exc_info:
        verify_auth(_request({
            "host": "backend:8914",
            "sec-fetch-site": "same-origin",
        }))

    assert exc_info.value.status_code == 401


def test_verify_auth_rejects_missing_token_without_browser_origin():
    with pytest.raises(HTTPException) as exc_info:
        verify_auth(_request({"host": "backend:8914"}))

    assert exc_info.value.status_code == 401


def test_verify_auth_extracts_token_from_cookie(monkeypatch):
    import app.auth as auth_mod
    import app.deps as deps
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: (
            {"sub": "user_cookie", "role": "user", "scope": "jti"}
            if t == "cookie-token"
            else None
        ),
    )
    monkeypatch.setattr(deps, "user_manager", None, raising=False)

    auth = verify_auth(
        _request(
            headers={"host": "backend:8914"},
            cookies={"session": "cookie-token"},
        )
    )
    assert auth["user_id"] == "user_cookie"
    assert auth["role"] == "user"
    assert auth["scope"] == "jti"
