"""Login API 測試 (app.routers.auth_routes)。

以 FastAPI TestClient 測試,不需 live Mongo 或真實 secret:
- 注入 fake deps.user_manager (verify_credentials 回已知 User / None)。
- SESSION_JWT_SECRET 以 monkeypatch 設定。

不依賴 bcrypt: fake user_manager 直接回 User,不走密碼雜湊。
PyJWT 已在 requirements,decode 驗證以 importorskip 守護。
"""

import importlib.util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.deps as deps
from app.routers.auth_routes import router as auth_router
from app.security.tokens import decode_session_token
from app.users import User

HAS_JWT = importlib.util.find_spec("jwt") is not None
requires_jwt = pytest.mark.skipif(not HAS_JWT, reason="PyJWT 未安裝")


class _FakeUserManager:
    """verify_credentials: 帳密為 alice/pw 時回固定 User,否則 None。"""

    def __init__(self, user: User):
        self._user = user

    def verify_credentials(self, username, password):
        if username == "alice" and password == "pw":
            return self._user
        return None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret-with-at-least-32-characters-long")
    user = User(
        id="user_abc",
        username="alice",
        password_hash="x",
        role="user",
        scope="jti",
    )
    monkeypatch.setattr(deps, "user_manager", _FakeUserManager(user), raising=False)

    test_app = FastAPI()
    test_app.include_router(auth_router)
    return TestClient(test_app)


def test_login_success_returns_token_role_scope(client):
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "user"
    assert body["scope"] == "jti"
    assert body["token"]


def test_login_success_sets_session_cookie(client):
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    assert "session" in resp.cookies
    assert resp.cookies["session"] == resp.json()["token"]


@requires_jwt
def test_login_token_claims(client):
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
    claims = decode_session_token(resp.json()["token"])
    assert claims is not None
    assert claims["sub"] == "user_abc"
    assert claims["role"] == "user"
    assert claims["scope"] == "jti"


def test_login_bad_credentials_returns_401_generic(client):
    resp = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401
    detail = resp.json()["detail"].lower()
    # 不洩漏是帳號還是密碼錯
    assert "password" not in detail
    assert "username" not in detail


def test_login_unknown_user_returns_401(client):
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": "pw"})
    assert resp.status_code == 401


def test_logout_returns_ok_and_clears_cookie(client):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # 清 cookie: Set-Cookie 應帶 session= 且過期
    set_cookie = resp.headers.get("set-cookie", "")
    assert "session=" in set_cookie
