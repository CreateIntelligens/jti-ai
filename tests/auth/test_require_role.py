"""verify_auth 的 session-JWT 分支與 require_role helper 測試。

層次:
- session JWT (valid) → verify_auth 回 role/app/store_name/user_id (取自 claims / user 查詢)。
- disabled user 帶 valid JWT → 401。
- ADMIN_API_KEY → role super_admin;require_role("super_admin") 通過。
- same-origin 無 token → 401。
- require_role 允許/拒絕 (403)。
- require_admin 接受 admin 與 super_admin。

純邏輯部分以 monkeypatch decode_session_token / deps.user_manager 完成,不需真 Mongo。
需要實際 JWT round-trip 的測試以 importorskip("jwt") 守護。
"""

import importlib.util
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.auth as auth_mod
import app.deps as deps
from app.auth import require_admin, require_role, verify_auth
from app.users import User

HAS_JWT = importlib.util.find_spec("jwt") is not None
requires_jwt = pytest.mark.skipif(not HAS_JWT, reason="PyJWT 未安裝")


def _request(headers: dict[str, str], query: dict | None = None, cookies: dict | None = None):
    return SimpleNamespace(headers=headers, query_params=query or {}, cookies=cookies or {})


def _bearer(token: str):
    return _request({"authorization": f"Bearer {token}"})


# --- session JWT branch (monkeypatched decode + user_manager) ---

def test_jwt_returns_role_scope_from_claims(monkeypatch):
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "user_abc", "role": "user", "scope": "jti"},
    )
    user = User(id="user_abc", username="alice", password_hash="x",
                role="user", scope="jti", store_name="store_jti")
    monkeypatch.setattr(deps, "user_manager",
                        SimpleNamespace(get_user=lambda uid: user), raising=False)

    auth = verify_auth(_bearer("any.jwt.token"))
    assert auth["role"] == "user"
    assert auth["scope"] == "jti"
    assert auth["store_name"] == "store_jti"
    assert auth["user_id"] == "user_abc"


def test_jwt_admin_role(monkeypatch):
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "user_admin", "role": "admin", "scope": None},
    )
    user = User(id="user_admin", username="boss", password_hash="x",
                role="admin", scope=None)
    monkeypatch.setattr(deps, "user_manager",
                        SimpleNamespace(get_user=lambda uid: user), raising=False)

    auth = verify_auth(_bearer("any.jwt"))
    assert auth["role"] == "admin"
    assert auth["scope"] is None


def test_jwt_disabled_user_raises_401(monkeypatch):
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "user_x", "role": "user", "scope": "jti"},
    )
    disabled = User(id="user_x", username="bob", password_hash="x",
                    role="user", scope="jti", disabled=True)
    monkeypatch.setattr(deps, "user_manager",
                        SimpleNamespace(get_user=lambda uid: disabled), raising=False)

    with pytest.raises(HTTPException) as exc:
        verify_auth(_bearer("any.jwt"))
    assert exc.value.status_code == 401


def test_jwt_unknown_user_raises_401(monkeypatch):
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "ghost", "role": "user", "scope": "jti"},
    )
    monkeypatch.setattr(deps, "user_manager",
                        SimpleNamespace(get_user=lambda uid: None), raising=False)

    with pytest.raises(HTTPException) as exc:
        verify_auth(_bearer("any.jwt"))
    assert exc.value.status_code == 401


def test_jwt_without_user_manager_uses_claims(monkeypatch):
    """deps.user_manager is None (測試環境) → 直接信任 claims。"""
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "user_abc", "role": "user", "scope": "general"},
    )
    monkeypatch.setattr(deps, "user_manager", None, raising=False)

    auth = verify_auth(_bearer("any.jwt"))
    assert auth["role"] == "user"
    assert auth["scope"] == "general"
    assert auth["user_id"] == "user_abc"


# --- ADMIN_API_KEY → super_admin ---

def test_admin_api_key_is_super_admin(monkeypatch):
    monkeypatch.setattr(auth_mod, "decode_session_token", lambda t: None)
    monkeypatch.setenv("ADMIN_API_KEY", "the-admin-key")
    auth = verify_auth(_bearer("the-admin-key"))
    assert auth["role"] == "super_admin"
    assert auth["store_name"] is None


# --- same-origin requests without tokens raise 401 ---

def test_same_origin_without_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        verify_auth(_request({
            "host": "backend:8914",
            "sec-fetch-site": "same-origin",
        }))
    assert exc.value.status_code == 401


# --- require_role ---

def test_require_role_allows_matching(monkeypatch):
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "u", "role": "user", "scope": "jti"},
    )
    monkeypatch.setattr(deps, "user_manager", None, raising=False)
    checker = require_role("user", "admin")
    auth = checker(_bearer("any.jwt"))
    assert auth["role"] == "user"


def test_require_role_denies_insufficient(monkeypatch):
    monkeypatch.setattr(
        auth_mod, "decode_session_token",
        lambda t: {"sub": "u", "role": "user", "scope": "jti"},
    )
    monkeypatch.setattr(deps, "user_manager", None, raising=False)
    checker = require_role("admin", "super_admin")
    with pytest.raises(HTTPException) as exc:
        checker(_bearer("any.jwt"))
    assert exc.value.status_code == 403


def test_require_role_super_admin_via_admin_api_key(monkeypatch):
    monkeypatch.setattr(auth_mod, "decode_session_token", lambda t: None)
    monkeypatch.setenv("ADMIN_API_KEY", "the-admin-key")
    checker = require_role("super_admin")
    auth = checker(_bearer("the-admin-key"))
    assert auth["role"] == "super_admin"


# --- require_admin back-compat ---

def test_require_admin_accepts_admin():
    require_admin({"role": "admin"})  # no raise


def test_require_admin_accepts_super_admin():
    require_admin({"role": "super_admin"})  # no raise


def test_require_admin_rejects_user():
    with pytest.raises(HTTPException) as exc:
        require_admin({"role": "user"})
    assert exc.value.status_code == 403


# --- real JWT round-trip via verify_auth (guarded) ---

@requires_jwt
def test_real_jwt_round_trip_through_verify_auth(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    monkeypatch.setattr(deps, "user_manager", None, raising=False)
    from app.security.tokens import create_session_token

    token = create_session_token("user_real", "user", "hciot")
    auth = verify_auth(_bearer(token))
    assert auth["role"] == "user"
    assert auth["scope"] == "hciot"
    assert auth["user_id"] == "user_real"


# --- GET /api/auth/me ---

def test_api_auth_me_returns_profile_info(monkeypatch):
    from fastapi.testclient import TestClient
    from tests.support.app_test_support import get_test_app

    app = get_test_app()
    client = TestClient(app)

    app.dependency_overrides[auth_mod.verify_auth] = lambda: {
        "role": "user",
        "scope": "hciot",
        "store_name": "store_a",
        "user_id": "user_id_123",
    }

    user = User(
        id="user_id_123",
        username="alice",
        password_hash="x",
        role="user",
        scope="hciot",
        store_name="store_a",
    )
    monkeypatch.setattr(
        deps,
        "user_manager",
        SimpleNamespace(get_user=lambda uid: user),
        raising=False,
    )

    try:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json() == {
            "user_id": "user_id_123",
            "username": "alice",
            "role": "user",
            "scope": "hciot",
            "store_name": "store_a",
        }
    finally:
        app.dependency_overrides.pop(auth_mod.verify_auth, None)


def test_api_auth_me_no_user_manager_returns_claims_only(monkeypatch):
    from fastapi.testclient import TestClient
    from tests.support.app_test_support import get_test_app

    app = get_test_app()
    client = TestClient(app)

    app.dependency_overrides[auth_mod.verify_auth] = lambda: {
        "role": "admin",
        "scope": None,
        "store_name": None,
        "user_id": "user_admin_123",
    }
    monkeypatch.setattr(deps, "user_manager", None, raising=False)

    try:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json() == {
            "user_id": "user_admin_123",
            "username": None,
            "role": "admin",
            "scope": None,
            "store_name": None,
        }
    finally:
        app.dependency_overrides.pop(auth_mod.verify_auth, None)
