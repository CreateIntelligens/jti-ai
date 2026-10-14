import json

import httpx
import pytest

from app.services import self_harm_classifier as clf

JEV = ("jev", "https://jev.test/v1/systemone", "jev-latest", "jev-key")
CLEF = ("clef", "https://clef.test/v1/systemone", "clef-flash", "")


@pytest.fixture
def anyio_backend():
    return "asyncio"


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _use_transport(monkeypatch, handler):
    monkeypatch.setattr(
        clf.httpx, "AsyncClient", lambda: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))
    )


def _answer(p):
    return httpx.Response(200, json={"answers": {"self_harm": {"noul": p}}})


@pytest.mark.anyio
async def test_jev_answer_is_used_without_asking_clef(monkeypatch):
    monkeypatch.setattr(clf, "_providers", lambda: [JEV, CLEF])
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers.get("authorization"), json.loads(request.content)))
        return _answer(0.1)

    _use_transport(monkeypatch, handler)
    assert await clf.classify_self_harm("好想睡著就不要再醒來") is False
    assert len(seen) == 1
    host, auth, body = seen[0]
    assert host == "jev.test" and auth == "Bearer jev-key"
    assert body["model"] == "jev-latest"
    assert body["state"] == {"message": "好想睡著就不要再醒來"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        httpx.Response(500),
        httpx.Response(200, json={"answers": {}}),
        httpx.Response(200, json={"answers": {"self_harm": {"noul": True}}}),
        httpx.Response(200, json={"answers": {"self_harm": {"noul": 1.5}}}),
        httpx.Response(200, content=b'{"answers": {"self_harm": {"noul": NaN}}}'),
    ],
)
async def test_jev_failure_falls_back_to_clef_without_auth_header(monkeypatch, bad):
    monkeypatch.setattr(clf, "_providers", lambda: [JEV, CLEF])
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers.get("authorization")))
        return bad if request.url.host == "jev.test" else _answer(0.9)

    _use_transport(monkeypatch, handler)
    assert await clf.classify_self_harm("我想吃掉一整罐安眠藥") is True
    assert seen == [("jev.test", "Bearer jev-key"), ("clef.test", None)]


@pytest.mark.anyio
async def test_all_providers_failing_returns_none_and_detect_uses_regex(monkeypatch):
    monkeypatch.setattr(clf, "_providers", lambda: [JEV, CLEF])

    def handler(request):
        raise httpx.ConnectError("down")

    _use_transport(monkeypatch, handler)
    assert await clf.classify_self_harm("我想從頂樓跳下去") is None
    assert await clf.detect_self_harm("我想從頂樓跳下去") is True
    assert await clf.detect_self_harm("好想睡著就不要再醒來") is False


@pytest.mark.anyio
async def test_unconfigured_classifier_never_calls_network(monkeypatch):
    def handler(request):
        raise AssertionError("should not call")

    _use_transport(monkeypatch, handler)
    assert await clf.classify_self_harm("我想從頂樓跳下去") is None
    monkeypatch.setattr(clf, "_providers", lambda: [JEV])
    assert await clf.classify_self_harm("") is None


def test_providers_follow_env(monkeypatch):
    monkeypatch.undo()
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("CLEF_URL", raising=False)
    assert clf._providers() == []
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setenv("CLEF_URL", "https://clef.test/v1/systemone")
    assert [p[0] for p in clf._providers()] == ["jev", "clef"]
    assert clf._providers()[0][1] == clf._DEFAULT_JEV_URL


@pytest.mark.anyio
async def test_recent_user_messages_are_sent_as_state(monkeypatch):
    monkeypatch.setattr(clf, "_providers", lambda: [JEV])
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["state"])
        return _answer(0.93)

    _use_transport(monkeypatch, handler)
    assert await clf.classify_self_harm("今晚就全部吃掉", ["我手邊有一整罐安眠藥"]) is True
    assert seen == [{"message": "今晚就全部吃掉", "recent_user_messages": ["我手邊有一整罐安眠藥"]}]


@pytest.mark.anyio
async def test_hanging_jev_is_cut_at_timeout_then_clef_answers(monkeypatch):
    import asyncio
    import time

    monkeypatch.setattr(clf, "_providers", lambda: [JEV, CLEF])
    monkeypatch.setenv("SELF_HARM_CLASSIFIER_TIMEOUT", "0.2")

    async def handler(request):
        if request.url.host == "jev.test":
            await asyncio.sleep(3)
        return _answer(0.9)

    _use_transport(monkeypatch, handler)
    started = time.monotonic()
    assert await clf.classify_self_harm("我想吃掉一整罐安眠藥") is True
    assert time.monotonic() - started < 1
