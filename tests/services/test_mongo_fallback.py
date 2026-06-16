import os
import pytest
from unittest.mock import patch

from app.services import mongo_client
from app.services.mongo_client import resolve_mongodb_uri, is_using_fallback


@pytest.fixture(autouse=True)
def reset_mongo_client_globals():
    """Reset the module-level globals in mongo_client to ensure test isolation."""
    mongo_client._resolved_uri = None
    mongo_client._using_fallback = False


def test_resolve_returns_primary_when_available():
    env_mock = {
        "MONGODB_URI": "mongodb://primary:27017",
        "MONGODB_URI_FALLBACK": "mongodb://fallback:27017",
    }
    with patch.dict(os.environ, env_mock), patch(
        "app.services.mongo_client._probe_mongodb_uri", return_value=(True, None)
    ) as mock_probe:
        uri = resolve_mongodb_uri()

        assert uri == "mongodb://primary:27017"
        assert is_using_fallback() is False
        mock_probe.assert_called_once_with("mongodb://primary:27017", mongo_client.MONGODB_PROBE_TIMEOUT_MS)


def test_resolve_falls_back_when_primary_unavailable():
    env_mock = {
        "MONGODB_URI": "mongodb://primary:27017",
        "MONGODB_URI_FALLBACK": "mongodb://fallback:27017",
    }
    with patch.dict(os.environ, env_mock), patch(
        "app.services.mongo_client._probe_mongodb_uri", return_value=(False, Exception("Connection refused"))
    ) as mock_probe:
        uri = resolve_mongodb_uri()

        assert uri == "mongodb://fallback:27017"
        assert is_using_fallback() is True
        mock_probe.assert_called_once_with("mongodb://primary:27017", mongo_client.MONGODB_PROBE_TIMEOUT_MS)


def test_resolve_returns_primary_without_probing_when_no_fallback_configured():
    env_mock = {
        "MONGODB_URI": "mongodb://primary:27017",
    }
    # If no fallback is configured, it should return primary without probing
    with patch.dict(os.environ, env_mock), patch(
        "app.services.mongo_client._probe_mongodb_uri"
    ) as mock_probe:
        if "MONGODB_URI_FALLBACK" in os.environ:
            del os.environ["MONGODB_URI_FALLBACK"]

        uri = resolve_mongodb_uri()

        assert uri == "mongodb://primary:27017"
        assert is_using_fallback() is False
        mock_probe.assert_not_called()
