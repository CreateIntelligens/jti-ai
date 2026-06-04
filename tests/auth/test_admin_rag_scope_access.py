from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import verify_auth
from app.routers.admin_rag import router


def _client_with_auth(auth: dict) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[verify_auth] = lambda: auth
    app.include_router(router)
    return TestClient(app)


def test_scope_user_can_read_own_app_rag_status():
    client = _client_with_auth({"role": "user", "scope": "hciot"})

    response = client.get("/api/admin/rag/status?source_type=hciot")

    assert response.status_code == 200
    assert response.json()["source_type"] == "hciot"


def test_scope_user_cannot_read_other_app_rag_status():
    client = _client_with_auth({"role": "user", "scope": "hciot"})

    response = client.get("/api/admin/rag/status?source_type=jti")

    assert response.status_code == 403


def test_scope_user_cannot_read_all_rag_status():
    client = _client_with_auth({"role": "user", "scope": "hciot"})

    response = client.get("/api/admin/rag/status?source_type=all")

    assert response.status_code == 403


def test_admin_can_read_all_rag_status():
    client = _client_with_auth({"role": "admin", "scope": "hciot"})

    response = client.get("/api/admin/rag/status?source_type=all")

    assert response.status_code == 200
    assert response.json()["source_type"] == "all"
