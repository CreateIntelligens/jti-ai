"""操作紀錄查詢僅供 super_admin，並在資料層套用篩選與分頁。"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import verify_auth
from app.routers import admin_audit
from app.services import audit_log


@pytest.fixture
def collection(monkeypatch):
    value = MagicMock()
    cursor = value.find.return_value
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.__iter__.return_value = iter([])
    value.count_documents.return_value = 0
    monkeypatch.setattr(audit_log, "get_audit_collection", lambda: value)
    if hasattr(admin_audit, "get_audit_collection"):
        monkeypatch.setattr(admin_audit, "get_audit_collection", lambda: value)
    return value


def _client(role=None):
    test_app = FastAPI()
    test_app.include_router(admin_audit.router)
    if role:
        test_app.dependency_overrides[verify_auth] = lambda: {
            "role": role, "user_id": "user_operator", "auth_method": "session",
        }
    return TestClient(test_app)


@pytest.mark.parametrize("role,status", [(None, 401), ("user", 403),
                                        ("admin", 403)])
def test_audit_read_requires_super_admin(collection, role, status):
    response = _client(role).get("/api/admin/audit-logs")
    assert response.status_code == status
    collection.find.assert_not_called()


def test_audit_filters_and_newest_first_pagination(collection):
    response = _client("super_admin").get(
        "/api/admin/audit-logs",
        params={"action": "user.create", "user_id": "user_operator",
                "username": "operator", "client_ip": "198.51.100.20",
                "since": "2026-01-01T00:00:00Z",
                "until": "2026-01-02T00:00:00Z", "limit": 20,
                "offset": 40},
    )
    assert response.status_code == 200
    assert response.json() == {
        "items": [], "total": 0, "limit": 20, "offset": 40,
    }
    query = collection.find.call_args.args[0]
    assert query == {
        "action": "user.create",
        "actor.user_id": "user_operator",
        "actor.username": "operator",
        "client_ip": "198.51.100.20",
        "timestamp": {
            "$gte": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "$lte": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
    }
    collection.count_documents.assert_called_once_with(query)
    cursor = collection.find.return_value
    cursor.sort.assert_called_once_with("timestamp", -1)
    cursor.skip.assert_called_once_with(40)
    cursor.limit.assert_called_once_with(20)


def test_audit_limit_is_capped(collection):
    response = _client("super_admin").get(
        "/api/admin/audit-logs", params={"limit": 1000},
    )
    assert response.status_code == 200
    assert response.json()["limit"] == 500
    collection.find.return_value.limit.assert_called_once_with(500)


def test_audit_serializes_timestamp_and_hides_mongo_id(collection):
    cursor = collection.find.return_value
    cursor.__iter__.return_value = iter([{
        "_id": "internal-object-id",
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "action": "user.create", "result": "success",
    }])
    collection.count_documents.return_value = 1
    response = _client("super_admin").get("/api/admin/audit-logs")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["timestamp"].startswith("2026-01-01T00:00:00")
    assert "_id" not in item
