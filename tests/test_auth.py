from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import verify_auth


def _request(headers: dict[str, str]):
    return SimpleNamespace(headers=headers, query_params={})


def test_verify_auth_allows_same_origin_via_forwarded_host():
    auth = verify_auth(_request({
        "host": "backend:8914",
        "x-forwarded-host": "10.9.0.32:8914",
        "origin": "http://10.9.0.32:8914",
    }))

    assert auth == {"role": "admin", "store_name": None}


def test_verify_auth_allows_browser_fetch_metadata_same_origin():
    auth = verify_auth(_request({
        "host": "backend:8914",
        "sec-fetch-site": "same-origin",
    }))

    assert auth == {"role": "admin", "store_name": None}


def test_verify_auth_rejects_missing_token_without_browser_origin():
    with pytest.raises(HTTPException) as exc_info:
        verify_auth(_request({"host": "backend:8914"}))

    assert exc_info.value.status_code == 401
