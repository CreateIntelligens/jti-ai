"""帳號管理 REST API 測試 (app/routers/general/users.py)。

不需真 Mongo / 真 secret:
- deps.user_manager 以 MagicMock 注入。
- 呼叫者角色透過 app.dependency_overrides 覆寫 users 路由的 require_role 守門依賴
  (users.require_admin_dep),每個測試回傳自訂 auth dict 模擬不同角色。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import app.deps as deps
from app.routers.general import users as users_mod
from app.users import User
from tests.support.app_test_support import get_test_app


app = get_test_app()


def _make_user(**kw) -> User:
    base = dict(username="u", password_hash="hash", role="user", app="general")
    base.update(kw)
    return User(**base)


def _override_auth(auth: dict):
    """覆寫 users 路由的守門依賴,回傳指定 auth dict。"""
    app.dependency_overrides[users_mod.require_admin_dep] = lambda: auth


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.pop(users_mod.require_admin_dep, None)
    deps.user_manager = None


@pytest.fixture
def client():
    return TestClient(app)


# --- GET /users ---

def test_admin_lists_users(client):
    deps.user_manager = MagicMock()
    deps.user_manager.list_users.return_value = [
        _make_user(id="user_1", username="alice"),
        _make_user(id="user_2", username="bob"),
    ]
    _override_auth({"role": "admin", "app": None, "store_name": None, "user_id": None})

    resp = client.get("/api/users")
    assert resp.status_code == 200
    body = resp.json()
    assert [u["username"] for u in body] == ["alice", "bob"]
    # password_hash 不可外洩
    assert all("password_hash" not in u for u in body)


# --- POST /users ---

def test_admin_creates_user_role_ok(client):
    deps.user_manager = MagicMock()
    deps.user_manager.create_user.return_value = _make_user(id="user_9", username="newbie")
    _override_auth({"role": "admin", "app": None, "store_name": None, "user_id": "admin_1"})

    resp = client.post("/api/users", json={
        "username": "newbie", "password": "pw", "role": "user", "app": "general",
    })
    assert resp.status_code in (200, 201)
    assert resp.json()["username"] == "newbie"
    assert "password_hash" not in resp.json()
    deps.user_manager.create_user.assert_called_once()


def test_admin_creating_admin_role_forbidden(client):
    deps.user_manager = MagicMock()
    _override_auth({"role": "admin", "app": None, "store_name": None, "user_id": "admin_1"})

    resp = client.post("/api/users", json={
        "username": "x", "password": "pw", "role": "admin",
    })
    assert resp.status_code == 403
    deps.user_manager.create_user.assert_not_called()


def test_super_admin_creates_admin_role_ok(client):
    deps.user_manager = MagicMock()
    deps.user_manager.create_user.return_value = _make_user(
        id="user_a", username="boss", role="admin", app=None)
    _override_auth({"role": "super_admin", "app": None, "store_name": None, "user_id": "su_1"})

    resp = client.post("/api/users", json={
        "username": "boss", "password": "pw", "role": "admin",
    })
    assert resp.status_code in (200, 201)
    assert resp.json()["role"] == "admin"


def test_create_duplicate_username_conflict(client):
    deps.user_manager = MagicMock()
    deps.user_manager.create_user.side_effect = DuplicateKeyError("dup")
    _override_auth({"role": "super_admin", "app": None, "store_name": None, "user_id": "su_1"})

    resp = client.post("/api/users", json={
        "username": "dup", "password": "pw", "role": "user", "app": "general",
    })
    assert resp.status_code == 409


def test_create_user_without_app_bad_request(client):
    deps.user_manager = MagicMock()
    deps.user_manager.create_user.side_effect = ValueError("role=user 必須指定非空的 app")
    _override_auth({"role": "super_admin", "app": None, "store_name": None, "user_id": "su_1"})

    resp = client.post("/api/users", json={
        "username": "noapp", "password": "pw", "role": "user",
    })
    assert resp.status_code == 400
    assert "app" in resp.json()["detail"]


# --- PATCH /users/{id}/disabled ---

def test_admin_disabling_admin_target_forbidden(client):
    deps.user_manager = MagicMock()
    deps.user_manager.get_user.return_value = _make_user(
        id="user_adm", username="other", role="admin", app=None)
    _override_auth({"role": "admin", "app": None, "store_name": None, "user_id": "admin_1"})

    resp = client.patch("/api/users/user_adm/disabled", json={"disabled": True})
    assert resp.status_code == 403
    deps.user_manager.set_disabled.assert_not_called()


def test_admin_disabling_user_target_ok(client):
    deps.user_manager = MagicMock()
    deps.user_manager.get_user.return_value = _make_user(
        id="user_t", username="target", role="user", app="general")
    deps.user_manager.set_disabled.return_value = True
    _override_auth({"role": "admin", "app": None, "store_name": None, "user_id": "admin_1"})

    resp = client.patch("/api/users/user_t/disabled", json={"disabled": True})
    assert resp.status_code == 200
    deps.user_manager.set_disabled.assert_called_once_with("user_t", True)


def test_super_admin_disabling_self_bad_request(client):
    deps.user_manager = MagicMock()
    deps.user_manager.get_user.return_value = _make_user(
        id="su_1", username="me", role="super_admin", app=None)
    _override_auth({"role": "super_admin", "app": None, "store_name": None, "user_id": "su_1"})

    resp = client.patch("/api/users/su_1/disabled", json={"disabled": True})
    assert resp.status_code == 400
    assert "self" in resp.json()["detail"].lower()
    deps.user_manager.set_disabled.assert_not_called()


# --- DELETE /users/{id} ---

def test_delete_missing_user_not_found(client):
    deps.user_manager = MagicMock()
    deps.user_manager.get_user.return_value = None
    _override_auth({"role": "super_admin", "app": None, "store_name": None, "user_id": "su_1"})

    resp = client.delete("/api/users/ghost")
    assert resp.status_code == 404


def test_super_admin_deletes_user_ok(client):
    deps.user_manager = MagicMock()
    deps.user_manager.get_user.return_value = _make_user(
        id="user_d", username="dead", role="user", app="general")
    deps.user_manager.delete_user.return_value = True
    _override_auth({"role": "super_admin", "app": None, "store_name": None, "user_id": "su_1"})

    resp = client.delete("/api/users/user_d")
    assert resp.status_code == 200
    deps.user_manager.delete_user.assert_called_once_with("user_d")


# --- role=user gate (require_role 403, 不覆寫依賴 → 走真實 verify_auth) ---

def test_plain_user_forbidden_on_every_endpoint(monkeypatch):
    """role=user 帶 session JWT → require_role 守門 403。"""
    deps.user_manager = None  # JWT 分支直接信任 claims
    import app.auth as auth_mod

    plain = TestClient(app)
    headers = {"authorization": "Bearer any.jwt"}

    monkeypatch.setattr(
        auth_mod,
        "decode_session_token",
        lambda t: {"sub": "u", "role": "user", "app": "general"},
    )

    assert plain.get("/api/users", headers=headers).status_code == 403
    assert plain.post(
        "/api/users",
        json={
            "username": "x", "password": "p", "role": "user", "app": "general",
        },
        headers=headers,
    ).status_code == 403
    assert plain.patch(
        "/api/users/u/disabled",
        json={"disabled": True},
        headers=headers,
    ).status_code == 403
    assert plain.delete("/api/users/u", headers=headers).status_code == 403
