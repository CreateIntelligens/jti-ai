"""Contracts for per-app endpoint isolation.

Two layers are covered:

1. Dedicated app endpoints (/api/jti, /api/hciot, /api/esg) guard with
   require_app_access(app): a key bound to one app must not reach another app's
   endpoints; super_admin/admin may cross.
2. The general /api/chat store resolution (_resolve_request_store): a key bound
   to a store may only chat with that store — a cross-store request is rejected
   (403) rather than silently rebound; admin may target any store.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_app_access, verify_auth
from app.routers.general.chat import ChatStartRequest, _resolve_request_store

ADMIN_AUTH = {"role": "super_admin", "store_name": None}


# ----- layer 1: dedicated endpoints via require_app_access ------------------

def _client_for_app(app_name: str, auth: dict) -> TestClient:
    api = FastAPI()
    api.dependency_overrides[verify_auth] = lambda: auth

    @api.post("/probe", dependencies=[Depends(require_app_access(app_name))])
    def _probe():
        return {"ok": True}

    return TestClient(api)


def _key_auth(app: str) -> dict:
    # sk-xxx style key bound to an app's managed store, no scope.
    store = {"jti": "__jti__", "hciot": "__hciot__", "esg": "__esg__"}[app]
    return {"role": "user", "store_name": store, "prompt_index": None}


@pytest.mark.parametrize("app_name", ["jti", "hciot", "esg"])
def test_key_can_access_its_own_app(app_name):
    client = _client_for_app(app_name, _key_auth(app_name))
    assert client.post("/probe").status_code == 200


@pytest.mark.parametrize(
    "key_app,endpoint_app",
    [
        ("jti", "hciot"), ("jti", "esg"),
        ("hciot", "jti"), ("hciot", "esg"),
        ("esg", "jti"), ("esg", "hciot"),
    ],
)
def test_key_cannot_access_other_app(key_app, endpoint_app):
    client = _client_for_app(endpoint_app, _key_auth(key_app))
    assert client.post("/probe").status_code == 403


@pytest.mark.parametrize("app_name", ["jti", "hciot", "esg"])
def test_admin_can_access_any_app(app_name):
    client = _client_for_app(app_name, ADMIN_AUTH)
    assert client.post("/probe").status_code == 200


# ----- layer 2: general store resolution ------------------------------------

def test_general_key_resolves_to_its_bound_store_without_request():
    auth = {"role": "user", "store_name": "__esg__", "prompt_index": None}
    assert _resolve_request_store(ChatStartRequest(), auth) == "__esg__"


def test_general_key_allows_request_for_its_own_store():
    auth = {"role": "user", "store_name": "__esg__", "prompt_index": None}
    resolved = _resolve_request_store(ChatStartRequest(store_name="__esg__"), auth)
    assert resolved == "__esg__"


@pytest.mark.parametrize(
    "bound,requested",
    [("__esg__", "__jti__"), ("__jti__", "__esg__"), ("__hciot__", "__jti__")],
)
def test_general_key_rejects_cross_store_request(bound, requested):
    auth = {"role": "user", "store_name": bound, "prompt_index": None}
    with pytest.raises(Exception) as exc:
        _resolve_request_store(ChatStartRequest(store_name=requested), auth)
    assert getattr(exc.value, "status_code", None) == 403


def test_general_admin_can_target_any_store():
    assert _resolve_request_store(
        ChatStartRequest(store_name="__hciot__"), ADMIN_AUTH
    ) == "__hciot__"
