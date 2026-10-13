"""Gemini key 被刪除或停用時要立刻換用別把，不能讓整個 app 的對話都失敗。"""
from unittest.mock import MagicMock, patch

import pytest

from app.services import gemini_clients as gc

KEY_INVALID = (
    "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. "
    "Please pass a valid API key.', 'status': 'INVALID_ARGUMENT', 'details': "
    "[{'reason': 'API_KEY_INVALID'}]}}"
)


@pytest.fixture
def registry(monkeypatch):
    clients = [MagicMock(name="poc"), MagicMock(name="jti"), MagicMock(name="esg")]
    monkeypatch.setattr(gc, "_clients", clients)
    monkeypatch.setattr(gc, "_key_names", ["POC1", "JTI", "和泰汽車"])
    monkeypatch.setattr(gc, "_dead_since", {})
    return clients


@pytest.mark.parametrize(
    "message,expected",
    [
        (KEY_INVALID, True),
        ("403 PERMISSION_DENIED. Your API key was reported as leaked.", True),
        ("401 UNAUTHENTICATED", True),
        ("429 RESOURCE_EXHAUSTED quota", False),
        ("503 UNAVAILABLE", False),
        ("404 NOT_FOUND model no longer available", False),
        ("400 INVALID_ARGUMENT", False),
    ],
)
def test_only_key_errors_trigger_failover(message, expected):
    assert gc.is_invalid_key_error(RuntimeError(message)) is expected


def test_dead_key_is_skipped_until_retry_window(registry):
    poc, _jti, esg = registry
    assert gc.get_client_by_index(2) is esg

    assert gc.mark_client_invalid(esg) is True
    assert gc.get_client_by_index(2) is poc

    with patch.object(gc.time, "monotonic", return_value=gc.time.monotonic() + gc._DEAD_KEY_RETRY_SECONDS + 1):
        assert gc.get_client_by_index(2) is esg


def test_default_client_skips_dead_first_key(registry):
    poc, jti, _esg = registry
    gc.mark_client_invalid(poc)
    assert gc.get_default_client() is jti


def test_all_keys_dead_reports_no_alternative(registry):
    poc, jti, esg = registry
    gc.mark_client_invalid(poc)
    gc.mark_client_invalid(jti)
    assert gc.mark_client_invalid(esg) is False
    # 全部失效時不吞掉錯誤：照舊回原本的 key，讓錯誤原樣浮出來
    assert gc.get_client_by_index(2) is esg


def test_probe_marks_only_invalid_keys(registry):
    poc, jti, esg = registry
    esg.models.list.side_effect = RuntimeError(KEY_INVALID)
    jti.models.list.side_effect = RuntimeError("503 UNAVAILABLE")
    poc.models.list.return_value = iter([object()])

    gc.probe_keys()

    assert set(gc._dead_since) == {2}
