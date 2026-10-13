"""確認操作紀錄、代理來源與敏感資料邊界，所有儲存均以替身隔離。"""

import json
import logging
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.deps as deps
from app.auth import verify_auth
from app.routers import auth_routes
from app.routers.general import api_keys, users
from app.services import audit_log
from app.users import User, UserManager


def _request(headers=None, peer="192.0.2.10"):
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/users",
        "headers": [
            (name.lower().encode(), value.encode())
            for name, value in (headers or {}).items()
        ],
        "client": (peer, 12345),
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    })


def _user(**changes):
    values = {
        "id": "user_sample",
        "username": "sample",
        "role": "user",
        "scope": "general",
        "password_hash": "stored-hash",
    }
    values.update(changes)
    return User(**values)


@pytest.fixture
def records(monkeypatch):
    captured = []
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setattr(audit_log, "_enqueue_record", captured.append)
    return captured


@pytest.fixture
def admin_auth():
    return {
        "role": "super_admin",
        "user_id": "user_operator",
        "username": "operator",
        "auth_method": "session",
    }


@pytest.mark.parametrize(
    "hops,headers,expected",
    [
        (1, {}, "192.0.2.10"),
        (1, {"X-Forwarded-For": "198.51.100.20"}, "198.51.100.20"),
        (1, {"X-Forwarded-For": "203.0.113.99, 198.51.100.20"},
         "198.51.100.20"),
        (2, {"X-Forwarded-For": "203.0.113.99, 198.51.100.20"},
         "203.0.113.99"),
        (2, {"X-Forwarded-For": "198.51.100.20"}, "192.0.2.10"),
        (0, {"X-Forwarded-For": "198.51.100.20"}, "192.0.2.10"),
        (1, {"X-Forwarded-For": "not-an-address"}, "192.0.2.10"),
        (1, {"X-Real-IP": "198.51.100.20"}, "198.51.100.20"),
        (1, {"Forwarded": 'for="[2001:db8::20]";proto=https'},
         "2001:db8::20"),
    ],
)
def test_client_ip_uses_configured_trusted_hops(
    monkeypatch, hops, headers, expected,
):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_HOPS", str(hops))
    assert audit_log.derive_client_ip(_request(headers)) == expected


def test_record_keeps_raw_chain_and_utc_timestamp(records, caplog):
    headers = {
        "X-Forwarded-For": "203.0.113.99, 198.51.100.20",
        "X-Real-IP": "198.51.100.20",
        "Forwarded": "for=198.51.100.20;proto=https",
        "User-Agent": "audit-test-client",
        "Authorization": "Bearer private-token-value",
    }
    with caplog.at_level(logging.INFO, logger=audit_log.__name__):
        audit_log.record_audit(
            _request(headers), "user.create", "success",
            actor={"role": "admin", "auth_method": "session"},
            target={"user_id": "user_target"},
        )
    assert len(records) == 1
    entry = records[0]
    assert entry["timestamp"].utcoffset() == timedelta(0)
    assert entry["peer_ip"] == "192.0.2.10"
    assert entry["client_ip"] == "198.51.100.20"
    assert entry["user_agent"] == "audit-test-client"
    assert entry["method"] == "POST"
    assert entry["path"] == "/api/users"
    for header in ("X-Forwarded-For", "X-Real-IP", "Forwarded"):
        assert headers[header] in json.dumps(entry["forwarded_chain"])
    assert "private-token-value" not in json.dumps(entry, default=str)
    with caplog.at_level(logging.INFO, logger=audit_log.__name__):
        audit_log._emit_file_record(entry)
    assert "user.create" in caplog.text
    assert "private-token-value" not in caplog.text


def _login_client(monkeypatch, user, valid):
    import app.users as user_module

    manager = UserManager.__new__(UserManager)
    manager.collection = MagicMock()
    manager.collection.find_one.return_value = user.model_dump() if user else None
    monkeypatch.setattr(user_module, "verify_password", lambda *args: valid)
    monkeypatch.setattr(deps, "user_manager", manager)
    monkeypatch.setenv(
        "SESSION_JWT_SECRET", "test-secret-with-at-least-32-characters-long",
    )
    test_app = FastAPI()
    test_app.include_router(auth_routes.router)
    return TestClient(test_app)


def test_login_success_records_actor_without_password_or_token(
    monkeypatch, records,
):
    client = _login_client(monkeypatch, _user(), True)
    response = client.post(
        "/api/auth/login",
        json={"username": "sample", "password": "private-password-value"},
        headers={"X-Forwarded-For": "198.51.100.20"},
    )
    assert response.status_code == 200
    assert len(records) == 1
    entry = records[0]
    assert entry["action"] == "auth.login"
    assert entry["result"] == "success"
    assert entry["actor"]["username"] == "sample"
    assert entry["actor"]["user_id"] == "user_sample"
    assert entry["client_ip"] == "198.51.100.20"
    serialized = json.dumps(entry, default=str)
    assert "private-password-value" not in serialized
    assert response.json()["token"] not in serialized


@pytest.mark.parametrize(
    "user,reason",
    [(None, "unknown_user"), (_user(), "bad_password"),
     (_user(disabled=True), "disabled")],
)
def test_login_failure_records_reason_but_keeps_response_generic(
    monkeypatch, records, user, reason,
):
    client = _login_client(monkeypatch, user, False)
    response = client.post(
        "/api/auth/login",
        json={"username": "sample", "password": "private-password-value"},
        headers={"X-Forwarded-For": "198.51.100.20"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert len(records) == 1
    entry = records[0]
    assert entry["action"] == "auth.login"
    assert entry["result"] == "failure"
    assert entry["reason"] == reason
    assert entry["actor"]["username"] == "sample"
    assert entry["client_ip"] == "198.51.100.20"
    assert "private-password-value" not in json.dumps(entry, default=str)


def test_user_create_records_actor_and_target_without_password(
    monkeypatch, records, admin_auth,
):
    manager = MagicMock()
    manager.create_user.return_value = _user()
    monkeypatch.setattr(deps, "user_manager", manager)
    test_app = FastAPI()
    test_app.include_router(users.router)
    test_app.dependency_overrides[users.require_admin_dep] = lambda: admin_auth
    response = TestClient(test_app).post(
        "/api/users",
        json={"username": "sample", "password": "private-password-value",
              "role": "user", "scope": "general"},
    )
    assert response.status_code in (200, 201)
    assert len(records) == 1
    entry = records[0]
    assert entry["action"] == "user.create"
    assert entry["result"] == "success"
    assert entry["actor"]["user_id"] == "user_operator"
    assert entry["actor"]["username"] == "operator"
    assert entry["actor"]["auth_method"] == "session"
    assert "sample" in json.dumps(entry["target"])
    assert "private-password-value" not in json.dumps(entry, default=str)
    assert "stored-hash" not in json.dumps(entry, default=str)


def test_key_reveal_records_actor_and_target_without_key(
    monkeypatch, records, admin_auth,
):
    manager = MagicMock()
    manager.get_key.return_value = MagicMock(id="key_sample")
    manager.reveal_key.return_value = "sk-private-key-value"
    monkeypatch.setattr(deps, "api_key_manager", manager)
    test_app = FastAPI()
    test_app.include_router(api_keys.router)
    test_app.dependency_overrides[verify_auth] = lambda: admin_auth
    response = TestClient(test_app).get("/api/keys/key_sample/reveal")
    assert response.status_code == 200
    assert response.json()["key"] == "sk-private-key-value"
    assert len(records) == 1
    entry = records[0]
    assert entry["action"] == "api_key.reveal"
    assert entry["actor"]["user_id"] == "user_operator"
    assert "key_sample" in json.dumps(entry["target"])
    assert "sk-private-key-value" not in json.dumps(entry, default=str)


def test_audit_queue_failure_does_not_break_login(monkeypatch, records):
    monkeypatch.setattr(
        audit_log, "_enqueue_record",
        MagicMock(side_effect=RuntimeError("storage unavailable")),
    )
    client = _login_client(monkeypatch, _user(), True)
    response = client.post(
        "/api/auth/login", json={"username": "sample", "password": "value"},
    )
    assert response.status_code == 200


def test_persistence_failure_is_contained(monkeypatch):
    monkeypatch.setattr(
        audit_log, "get_audit_collection",
        MagicMock(side_effect=RuntimeError("storage unavailable")),
    )
    audit_log._persist_record({"action": "user.create"})


@pytest.mark.parametrize(
    "payload,status,reason",
    [({"username": "sample"}, 422, "validation_error"),
     ({"username": "sample", "password": "value", "role": "admin"},
      403, None)],
)
def test_rejected_mutation_still_records_failure(
    monkeypatch, records, payload, status, reason,
):
    monkeypatch.setattr(deps, "user_manager", MagicMock())
    test_app = FastAPI()
    test_app.include_router(users.router)
    test_app.dependency_overrides[users.require_admin_dep] = lambda: {
        "role": "admin", "user_id": "user_operator", "auth_method": "session",
    }
    response = TestClient(test_app).post("/api/users", json=payload)
    assert response.status_code == status
    assert len(records) == 1
    assert records[0]["action"] == "user.create"
    assert records[0]["result"] == "failure"
    if reason:
        assert reason in records[0]["reason"]


def test_mongo_persistence_initializes_expected_indexes(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(audit_log, "get_audit_collection", lambda: collection)
    monkeypatch.setattr(audit_log, "_indexes_ready", False)
    record = {"action": "user.create", "result": "success"}
    audit_log._persist_record(record)
    assert [call.args[0] for call in collection.create_index.call_args_list] == [
        [("timestamp", -1)], [("action", 1)], [("client_ip", 1)],
        [("actor.user_id", 1)],
    ]
    collection.insert_one.assert_called_once_with(record)


def test_index_failure_still_attempts_record_write(monkeypatch):
    collection = MagicMock()
    collection.create_index.side_effect = RuntimeError("index unavailable")
    monkeypatch.setattr(audit_log, "get_audit_collection", lambda: collection)
    monkeypatch.setattr(audit_log, "_indexes_ready", False)
    audit_log._persist_record({"action": "user.create"})
    collection.insert_one.assert_called_once()


@pytest.mark.parametrize("method", ["session", "admin_api_key", "api_key"])
def test_authentication_records_method_without_credential(
    monkeypatch, records, method,
):
    import app.auth as auth_mod

    secret = "sk-private-authentication-value"
    request = _request({"Authorization": f"Bearer {secret}"})
    manager = MagicMock()
    monkeypatch.setattr(deps, "user_manager", manager)
    manager.get_user.return_value = _user(username="operator")
    key_manager = MagicMock()
    key_manager.verify_key.return_value = MagicMock(
        id="key_actor", key_prefix="sk-private...", store_name="store_sample",
        prompt_index=0,
    )
    monkeypatch.setattr(deps, "api_key_manager", key_manager)
    if method == "session":
        monkeypatch.setattr(auth_mod, "decode_session_token", lambda token: {
            "role": "user", "sub": "user_sample", "scope": "general",
        })
    else:
        monkeypatch.setattr(auth_mod, "decode_session_token", lambda token: None)
    if method == "admin_api_key":
        monkeypatch.setenv("ADMIN_API_KEY", secret)
    else:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    context = audit_log._request_context.set(request)
    try:
        auth_mod.verify_auth(request)
    finally:
        audit_log._request_context.reset(context)
    audit_log.record_audit(request, "prompt.update", "success")
    actor = records[0]["actor"]
    assert actor["auth_method"] == method
    if method == "session":
        assert actor["user_id"] == "user_sample"
        assert actor["username"] == "operator"
    if method == "api_key":
        assert actor["api_key_id"] == "key_actor"
        assert actor["api_key_prefix"]
    assert secret not in json.dumps(records[0], default=str)


def test_unauthenticated_mutation_records_anonymous_failure(
    monkeypatch, records,
):
    manager = MagicMock()
    monkeypatch.setattr(deps, "user_manager", manager)
    test_app = FastAPI()
    test_app.include_router(users.router)
    response = TestClient(test_app).post(
        "/api/users",
        json={"username": "sample", "password": "private-password-value",
              "role": "user", "scope": "general"},
    )
    assert response.status_code == 401
    manager.create_user.assert_not_called()
    assert len(records) == 1
    assert records[0]["action"] == "user.create"
    assert records[0]["result"] == "failure"
    assert records[0]["actor"]["auth_method"] == "anonymous"
    assert "private-password-value" not in json.dumps(records[0], default=str)


def test_record_entry_point_removes_sensitive_metadata(records):
    audit_log.record_audit(
        _request(), "user.create", "success",
        actor={"role": "admin", "auth_method": "session",
               "password": "actor-private", "token": "actor-token"},
        target={"user_id": "user_target", "password": "target-private",
                "key": "target-key", "content": "upload-private"},
    )
    entry = records[0]
    assert entry["target"] == {"user_id": "user_target"}
    serialized = json.dumps(entry, default=str)
    for private in (
        "actor-private", "actor-token", "target-private", "target-key",
        "upload-private",
    ):
        assert private not in serialized


def test_duplicate_forwarded_headers_walk_from_right(records):
    request = _request({"X-Forwarded-For": "203.0.113.99"})
    request.scope["headers"].append(
        (b"x-forwarded-for", b"198.51.100.20"),
    )
    audit_log.record_audit(request, "user.create", "success")
    assert records[0]["client_ip"] == "198.51.100.20"
    assert records[0]["forwarded_chain"]["x-forwarded-for"] == (
        "203.0.113.99,198.51.100.20"
    )


def test_login_validation_failure_retains_submitted_username(records):
    test_app = FastAPI()
    test_app.include_router(auth_routes.router)
    response = TestClient(test_app).post(
        "/api/auth/login", json={"username": "sample"},
        headers={"X-Forwarded-For": "198.51.100.20"},
    )
    assert response.status_code == 422
    assert records[0]["actor"]["username"] == "sample"
    assert records[0]["client_ip"] == "198.51.100.20"
    assert records[0]["result"] == "failure"
    assert records[0]["reason"] == "validation_error"


def test_disabled_session_records_identity_without_extra_lookup(
    monkeypatch, records,
):
    import app.auth as auth_mod

    user = _user(disabled=True)
    manager = MagicMock()
    manager.get_user.return_value = user
    monkeypatch.setattr(deps, "user_manager", manager)
    monkeypatch.setattr(auth_mod, "decode_session_token", lambda token: {
        "role": "user", "sub": user.id, "scope": "general",
    })
    test_app = FastAPI()
    test_app.include_router(users.router)
    response = TestClient(test_app).delete(
        "/api/users/user_target", headers={"Authorization": "Bearer sample"},
    )
    assert response.status_code == 401
    assert records[0]["actor"]["username"] == user.username
    assert records[0]["actor"]["user_id"] == user.id
    assert records[0]["actor"]["auth_method"] == "session"
    manager.get_user.assert_called_once_with(user.id)
    manager.delete_user.assert_not_called()


def test_operation_target_is_distinct_from_actor(monkeypatch, records):
    manager = MagicMock()
    target = _user(id="user_target")
    manager.get_user.return_value = target
    manager.delete_user.return_value = True
    monkeypatch.setattr(deps, "user_manager", manager)
    test_app = FastAPI()
    test_app.include_router(users.router)
    test_app.dependency_overrides[users.require_admin_dep] = lambda: {
        "role": "super_admin", "user_id": "user_operator",
        "auth_method": "session",
    }
    response = TestClient(test_app).delete("/api/users/user_target")
    assert response.status_code == 200
    assert records[0]["target"]["user_id"] == "user_target"
    assert records[0]["actor"]["user_id"] == "user_operator"


def test_login_identity_lookup_failure_keeps_generic_response(
    monkeypatch, records,
):
    manager = MagicMock()
    manager.verify_credentials.return_value = None
    manager.get_by_username.side_effect = RuntimeError("private-detail")
    monkeypatch.setattr(deps, "user_manager", manager)
    test_app = FastAPI()
    test_app.include_router(auth_routes.router)
    response = TestClient(test_app).post(
        "/api/auth/login", json={"username": "sample", "password": "bad"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert records[0]["reason"] == "credentials_rejected"
    manager.get_by_username.assert_not_called()
    assert "private-detail" not in json.dumps(records[0], default=str)


@pytest.mark.parametrize("module_name", ["admin_rag", "general.knowledge"])
def test_reindex_records_acceptance_without_changing_background_work(
    monkeypatch, records, module_name,
):
    import importlib

    from app.auth import verify_admin

    module = importlib.import_module(f"app.routers.{module_name}")
    scheduled = []

    def schedule(coroutine):
        scheduled.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(module.asyncio, "create_task", schedule)
    test_app = FastAPI()
    test_app.dependency_overrides[verify_admin] = lambda: {"role": "admin"}
    test_app.dependency_overrides[verify_auth] = lambda: {
        "role": "admin", "user_id": "user_operator", "auth_method": "session",
    }
    if module_name == "admin_rag":
        test_app.include_router(module.router)
        path = "/api/admin/rag/reindex?source_type=hciot"
    else:
        test_app.include_router(module._reindex_router, prefix="/knowledge")
        path = "/knowledge/reindex?language=store_sample"
    response = TestClient(test_app).post(path)
    assert response.status_code == 200
    assert response.json()["started"] is True
    assert len(scheduled) == 1
    assert records[0]["action"] == "rag.reindex"
    assert records[0]["result"] == "success"
    assert records[0]["reason"] == "accepted"
