import os
import sys
import importlib
import pytest
from unittest.mock import patch


@pytest.fixture
def restore_real_mongo_client():
    """Ensure the real mongo_client module is loaded for this test.

    If a MagicMock was globally installed in sys.modules by other tests,
    temporarily restore the real implementation and clean up afterwards.
    """
    orig_module = sys.modules.get("app.services.mongo_client")
    mock_present = orig_module is not None and not hasattr(orig_module, "__file__")

    if mock_present:
        del sys.modules["app.services.mongo_client"]

    import app.services.mongo_client as real_mongo
    importlib.reload(real_mongo)

    # Reset module-level globals in the real mongo_client
    real_mongo._resolved_uri = None
    real_mongo._using_fallback = False

    yield real_mongo

    if mock_present:
        sys.modules["app.services.mongo_client"] = orig_module


def test_resolve_returns_primary_when_available(restore_real_mongo_client):
    mongo_module = restore_real_mongo_client
    env_mock = {
        "MONGODB_URI": "mongodb://primary:27017",
        "MONGODB_URI_FALLBACK": "mongodb://fallback:27017",
    }
    with patch.dict(os.environ, env_mock), patch(
        "app.services.mongo_client._probe_mongodb_uri", return_value=(True, None)
    ) as mock_probe:
        uri = mongo_module.resolve_mongodb_uri()

        assert uri == "mongodb://primary:27017"
        assert mongo_module.is_using_fallback() is False
        mock_probe.assert_called_once_with("mongodb://primary:27017", mongo_module.MONGODB_PROBE_TIMEOUT_MS)


def test_resolve_falls_back_when_primary_unavailable(restore_real_mongo_client):
    mongo_module = restore_real_mongo_client
    env_mock = {
        "MONGODB_URI": "mongodb://primary:27017",
        "MONGODB_URI_FALLBACK": "mongodb://fallback:27017",
    }
    with patch.dict(os.environ, env_mock), patch(
        "app.services.mongo_client._probe_mongodb_uri", return_value=(False, Exception("Connection refused"))
    ) as mock_probe:
        uri = mongo_module.resolve_mongodb_uri()

        assert uri == "mongodb://fallback:27017"
        assert mongo_module.is_using_fallback() is True
        mock_probe.assert_called_once_with("mongodb://primary:27017", mongo_module.MONGODB_PROBE_TIMEOUT_MS)


def test_resolve_returns_primary_without_probing_when_no_fallback_configured(restore_real_mongo_client):
    mongo_module = restore_real_mongo_client
    env_mock = {
        "MONGODB_URI": "mongodb://primary:27017",
    }
    # If no fallback is configured, it should return primary without probing
    with patch.dict(os.environ, env_mock), patch(
        "app.services.mongo_client._probe_mongodb_uri"
    ) as mock_probe:
        if "MONGODB_URI_FALLBACK" in os.environ:
            del os.environ["MONGODB_URI_FALLBACK"]

        uri = mongo_module.resolve_mongodb_uri()

        assert uri == "mongodb://primary:27017"
        assert mongo_module.is_using_fallback() is False
        mock_probe.assert_not_called()
