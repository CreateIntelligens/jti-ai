"""觀察功能不得改變既有回應，所有 I/O 都使用隔離替身。"""

import http.cookies
import threading
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import app.deps as deps
from app.auth import verify_auth
from app.routers import auth_routes
from app.routers._shared import qa_kb_router, qa_kb_upload
from app.routers.general import api_keys, users
from app.services import audit_log
from app.users import User

_REAL_CAPTURE = audit_log._capture_metadata
_REAL_ENQUEUE = audit_log._enqueue_record
_REAL_EMIT = audit_log._emit_file_record
_REAL_REPORT = audit_log.record_audit
_ADMIN = {
    "role": "super_admin", "user_id": "user_operator",
    "username": "operator", "auth_method": "session",
}


def _user(**changes):
    values = {
        "id": "user_sample", "username": "sample", "password_hash": "hash",
        "role": "user", "scope": "general", "disabled": False,
        "created_at": "2025-01-01T00:00:00+00:00",
    }
    values.update(changes)
    return User(**values)


def _response_signature(response):
    return (
        response.status_code, response.content, response.headers.raw,
        sorted(response.cookies.items()),
    )


def _client(router):
    test_app = FastAPI()
    test_app.include_router(router)
    return TestClient(test_app, raise_server_exceptions=False)


def _compare_modes(monkeypatch, exercise, *, require_records=True):
    signatures = []
    records = []
    for mode in ("disabled", "enabled", "raising"):
        with monkeypatch.context() as patch:
            patch.setattr(audit_log, "_enqueue_record", records.append)
            patch.setattr(audit_log, "record_audit", _REAL_REPORT)
            patch.setattr(audit_log, "_capture_metadata", _REAL_CAPTURE)
            if mode == "disabled":
                patch.setattr(audit_log, "record_audit", lambda *a, **k: None)
                patch.setattr(audit_log, "_capture_metadata", lambda *a, **k: None)
            elif mode == "raising":
                patch.setattr(
                    audit_log, "record_audit",
                    MagicMock(side_effect=RuntimeError("report unavailable")),
                )
                patch.setattr(
                    audit_log, "_capture_metadata",
                    MagicMock(side_effect=RuntimeError("metadata unavailable")),
                )
            signatures.append(_response_signature(exercise(patch)))
    assert signatures[0] == signatures[1] == signatures[2]
    if require_records:
        assert records
    return signatures[0]


@pytest.mark.parametrize(
    "case,status",
    [("success", 200), ("unknown_user", 401), ("bad_password", 401),
     ("disabled", 401), ("validation", 422), ("no_manager", 500),
     ("manager_error", 500), ("token_error", 500)],
)
def test_login_responses_are_identical_in_all_audit_modes(
    monkeypatch, case, status,
):
    def exercise(patch):
        manager = MagicMock()
        user = _user(disabled=case == "disabled")
        manager.verify_credentials.return_value = (
            user if case in {"success", "token_error"} else None
        )
        manager.get_by_username.return_value = (
            None if case == "unknown_user" else user
        )
        if case == "manager_error":
            manager.verify_credentials.side_effect = RuntimeError("unavailable")
        patch.setattr(deps, "user_manager", None if case == "no_manager" else manager)
        token = MagicMock(return_value="fixed-session-token")
        if case == "token_error":
            token.side_effect = RuntimeError("signing unavailable")
        patch.setattr(auth_routes, "create_session_token", token)
        payload = {"username": "sample", "password": "value"}
        if case == "validation":
            payload.pop("password")
        response = _client(auth_routes.router).post("/api/auth/login", json=payload)
        if case not in {"validation", "no_manager"}:
            manager.verify_credentials.assert_called_once_with("sample", "value")
        return response

    signature = _compare_modes(monkeypatch, exercise)
    assert signature[0] == status


def test_logout_clears_cookie_without_any_auth_verification(monkeypatch):
    monkeypatch.setattr(
        http.cookies, "_getdate", lambda future=0: "Thu, 01 Jan 1970 00:00:00 GMT",
    )
    verify = MagicMock(side_effect=RuntimeError("must not verify"))
    monkeypatch.setattr(auth_routes, "verify_auth", verify)

    def exercise(patch):
        return _client(auth_routes.router).post(
            "/api/auth/logout", headers={"Cookie": "session=old-session"},
        )

    assert _compare_modes(
        monkeypatch, exercise, require_records=False,
    )[0] == 200
    verify.assert_not_called()


@pytest.mark.parametrize(
    "case,status",
    [("create", 201), ("create_duplicate", 409), ("create_forbidden", 403),
     ("disable", 200), ("disable_missing", 404), ("disable_forbidden", 403),
     ("delete", 200), ("delete_missing", 404), ("delete_forbidden", 403)],
)
def test_user_mutation_responses_are_identical_in_all_audit_modes(
    monkeypatch, case, status,
):
    def exercise(patch):
        manager = MagicMock()
        manager.create_user.return_value = _user()
        manager.get_user.return_value = (
            None if case.endswith("missing")
            else _user(role="admin", scope=None) if case.endswith("forbidden")
            else _user()
        )
        manager.set_disabled.return_value = True
        manager.delete_user.return_value = True
        if case == "create_duplicate":
            manager.create_user.side_effect = DuplicateKeyError("duplicate")
        patch.setattr(deps, "user_manager", manager)
        auth = {**_ADMIN, "role": "admin"} if case.endswith("forbidden") else _ADMIN
        client = _client(users.router)
        client.app.dependency_overrides[users.require_admin_dep] = lambda: auth
        if case.startswith("create"):
            response = client.post("/api/users", json={
                "username": "sample", "password": "value",
                "role": "admin" if case.endswith("forbidden") else "user",
                "scope": "general",
            })
        elif case.startswith("disable"):
            response = client.patch(
                "/api/users/user_sample/disabled", json={"disabled": True},
            )
        else:
            response = client.delete("/api/users/user_sample")
        return response

    assert _compare_modes(monkeypatch, exercise)[0] == status


def _key():
    return SimpleNamespace(
        id="key_sample", key_prefix="sk-sample...", name="sample-key",
        store_name="store_sample", prompt_index=0,
        created_at="2025-01-01T00:00:00+00:00", last_used_at=None,
    )


@pytest.mark.parametrize(
    "case,status",
    [("create", 200), ("create_forbidden", 403),
     ("update", 200), ("update_missing", 404), ("update_forbidden", 403),
     ("delete", 200), ("delete_missing", 404), ("delete_forbidden", 403),
     ("reveal", 200), ("reveal_missing", 404), ("reveal_conflict", 409),
     ("reveal_forbidden", 404)],
)
def test_key_mutation_responses_are_identical_in_all_audit_modes(
    monkeypatch, case, status,
):
    def exercise(patch):
        manager = MagicMock()
        manager.create_key.return_value = (_key(), "sk-fixed-key-value")
        manager.get_key.return_value = None if case == "reveal_missing" else _key()
        manager.update_key.return_value = None if case == "update_missing" else _key()
        manager.delete_key.return_value = case != "delete_missing"
        manager.reveal_key.return_value = "sk-fixed-key-value"
        if case == "reveal_conflict":
            manager.reveal_key.side_effect = ValueError("key unavailable")
        patch.setattr(deps, "api_key_manager", manager)
        patch.setattr(
            api_keys, "_visible_store_names",
            lambda auth, request: (
                None if auth.get("role") in {"admin", "super_admin"} else set()
            ),
        )
        auth = {**_ADMIN, "role": "user"} if case.endswith("forbidden") else _ADMIN
        client = _client(api_keys.router)
        client.app.dependency_overrides[verify_auth] = lambda: auth
        if case.startswith("create"):
            return client.post("/api/keys", json={
                "name": "sample-key", "store_name": "store_sample",
            })
        if case.startswith("update"):
            return client.put("/api/keys/key_sample", json={"name": "renamed"})
        if case.startswith("delete"):
            return client.delete("/api/keys/key_sample")
        return client.get("/api/keys/key_sample/reveal")

    assert _compare_modes(monkeypatch, exercise)[0] == status


@pytest.mark.parametrize("operation", ["upload", "update", "delete"])
def test_shared_knowledge_mutations_are_identical_in_all_audit_modes(
    monkeypatch, operation,
):
    def exercise(patch):
        store = MagicMock()
        store.list_files.return_value = []
        store.insert_file.return_value = {
            "name": "guide.txt", "display_name": "guide.txt", "size": 7,
        }
        store.get_file.return_value = {
            "filename": "guide.txt", "topic_id": None,
            "data": b"content", "content_type": "text/plain",
        }
        store.update_file_content.return_value = True
        store.delete_file.return_value = True
        patch.setattr(qa_kb_router, "check_upload_rate_limit", lambda request: None)
        patch.setattr(qa_kb_upload, "sync_to_rag", lambda *a: None)
        patch.setattr(qa_kb_upload, "delete_from_rag", lambda *a: None)
        patch.setattr(qa_kb_router, "require_kb_access", lambda app: lambda: _ADMIN)
        config = qa_kb_router.QaKbRouterConfig(
            tag="Test KB", app="hciot",
            knowledge_store_factory=lambda: store,
            topic_store_factory=lambda language: MagicMock(),
            rag_source_type="hciot", invalidate_cache=lambda language=None: None,
            other_language=lambda language: "en" if language == "zh" else "zh",
        )
        client = _client(qa_kb_router.build_qa_kb_router(config, include_knowledge=True))
        if operation == "upload":
            response = client.post(
                "/upload/", files={"file": ("guide.txt", b"content", "text/plain")},
            )
            store.insert_file.assert_called_once()
            assert store.insert_file.call_args.kwargs["data"] == b"content"
        elif operation == "update":
            response = client.put(
                "/files/guide.txt/content", json={"content": "changed"},
            )
            store.update_file_content.assert_called_once()
        else:
            response = client.delete("/files/guide.txt")
            store.delete_file.assert_called_once()
        return response

    assert _compare_modes(monkeypatch, exercise)[0] == 200


@pytest.fixture
def background_writer(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(audit_log, "_pending", Queue(maxsize=4))
    monkeypatch.setattr(audit_log, "_worker_lock", threading.Lock())
    monkeypatch.setattr(audit_log, "_worker", None)
    monkeypatch.setattr(audit_log, "_indexes_ready", True)
    monkeypatch.setattr(audit_log, "get_audit_collection", lambda: collection)
    monkeypatch.setattr(audit_log, "_emit_file_record", MagicMock())
    monkeypatch.setattr(audit_log, "_enqueue_record", _REAL_ENQUEUE)
    try:
        yield collection
    finally:
        worker = audit_log._worker
        if worker is not None and worker.is_alive():
            audit_log._pending.put(None, timeout=2)
            worker.join(timeout=5)
            assert not worker.is_alive()


def _background_login_client(monkeypatch, request_threads):
    manager = MagicMock()

    def verify(username, password):
        request_threads.append(threading.get_ident())
        return _user()

    manager.verify_credentials.side_effect = verify
    monkeypatch.setattr(deps, "user_manager", manager)
    monkeypatch.setattr(auth_routes, "create_session_token", lambda *a: "fixed-token")
    return _client(auth_routes.router)


@pytest.mark.parametrize("component", ["mongo", "file"])
def test_blocked_background_storage_does_not_delay_response(
    monkeypatch, background_writer, component,
):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    response_ready = threading.Event()
    request_threads = []
    storage_threads = []
    responses = []

    def blocked_write(record):
        storage_threads.append(threading.get_ident())
        started.set()
        try:
            assert release.wait(timeout=5)
        finally:
            finished.set()

    if component == "mongo":
        background_writer.insert_one.side_effect = blocked_write
    else:
        monkeypatch.setattr(audit_log, "_emit_file_record", blocked_write)
    client = _background_login_client(monkeypatch, request_threads)

    def request():
        responses.append(client.post(
            "/api/auth/login", json={"username": "sample", "password": "value"},
        ))
        response_ready.set()

    request_thread = threading.Thread(target=request)
    request_thread.start()
    try:
        assert started.wait(timeout=2)
        assert response_ready.wait(timeout=2)
        assert not release.is_set()
        assert not finished.is_set()
        assert responses[0].status_code == 200
        assert storage_threads[0] not in request_threads
        assert storage_threads[0] != request_thread.ident
    finally:
        release.set()
        request_thread.join(timeout=5)
        assert not request_thread.is_alive()
        assert finished.wait(timeout=5)


def test_background_mongo_failure_keeps_response_and_warns(
    monkeypatch, background_writer, caplog,
):
    completed = threading.Event()

    def failed_write(record):
        completed.set()
        raise RuntimeError("write unavailable")

    background_writer.insert_one.side_effect = failed_write
    client = _background_login_client(monkeypatch, [])
    response = client.post(
        "/api/auth/login", json={"username": "sample", "password": "value"},
    )
    assert response.status_code == 200
    assert completed.wait(timeout=2)
    worker = audit_log._worker
    audit_log._pending.put(None, timeout=2)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert "Audit database write failed" in caplog.text


def test_busy_audit_lock_does_not_delay_response(monkeypatch, background_writer):
    response_ready = threading.Event()
    responses = []
    client = _background_login_client(monkeypatch, [])

    def request():
        responses.append(client.post(
            "/api/auth/login", json={"username": "sample", "password": "value"},
        ))
        response_ready.set()

    lock = audit_log._worker_lock
    lock.acquire()
    thread = threading.Thread(target=request)
    thread.start()
    try:
        assert response_ready.wait(timeout=2)
        assert responses[0].status_code == 200
    finally:
        lock.release()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_full_audit_queue_keeps_response(monkeypatch):
    queue = Queue(maxsize=1)
    queue.put_nowait({"action": "user.create"})
    collection = MagicMock()
    monkeypatch.setattr(audit_log, "_pending", queue)
    monkeypatch.setattr(audit_log, "_worker_lock", threading.Lock())
    monkeypatch.setattr(audit_log, "_worker", None)
    monkeypatch.setattr(audit_log, "_enqueue_record", _REAL_ENQUEUE)
    monkeypatch.setattr(audit_log, "get_audit_collection", lambda: collection)
    client = _background_login_client(monkeypatch, [])
    response = client.post(
        "/api/auth/login", json={"username": "sample", "password": "value"},
    )
    assert response.status_code == 200
    assert response.json()["token"] == "fixed-token"
    assert audit_log._worker is None
    collection.insert_one.assert_not_called()


def test_file_and_warning_logger_failure_keeps_response_and_mongo_write(
    monkeypatch, background_writer,
):
    inserted = threading.Event()
    monkeypatch.setattr(audit_log, "_emit_file_record", _REAL_EMIT)
    monkeypatch.setattr(
        audit_log.logger, "info",
        MagicMock(side_effect=RuntimeError("file unavailable")),
    )
    monkeypatch.setattr(
        audit_log.logger, "warning",
        MagicMock(side_effect=RuntimeError("warning unavailable")),
    )
    background_writer.insert_one.side_effect = lambda record: inserted.set()
    client = _background_login_client(monkeypatch, [])
    response = client.post(
        "/api/auth/login", json={"username": "sample", "password": "value"},
    )
    assert response.status_code == 200
    assert inserted.wait(timeout=2)
    background_writer.insert_one.assert_called_once()


def test_blocked_warning_logger_after_reporter_failure_keeps_response(
    monkeypatch, background_writer,
):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    response_ready = threading.Event()
    request_threads = []
    warning_threads = []
    responses = []

    def blocked_warning(message):
        warning_threads.append(threading.get_ident())
        started.set()
        try:
            assert release.wait(timeout=5)
        finally:
            finished.set()

    monkeypatch.setattr(audit_log.logger, "warning", blocked_warning)
    monkeypatch.setattr(
        audit_log, "record_audit",
        MagicMock(side_effect=RuntimeError("report unavailable")),
    )
    client = _background_login_client(monkeypatch, request_threads)

    def request():
        responses.append(client.post(
            "/api/auth/login", json={"username": "sample", "password": "value"},
        ))
        response_ready.set()

    thread = threading.Thread(target=request)
    thread.start()
    try:
        assert started.wait(timeout=2)
        assert response_ready.wait(timeout=2)
        assert not release.is_set()
        assert not finished.is_set()
        assert responses[0].status_code == 200
        assert responses[0].json()["token"] == "fixed-token"
        assert warning_threads[0] == audit_log._worker.ident
        assert warning_threads[0] not in request_threads
        assert warning_threads[0] != thread.ident
        background_writer.insert_one.assert_not_called()
    finally:
        release.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert finished.wait(timeout=5)
