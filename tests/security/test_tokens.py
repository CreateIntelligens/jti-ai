"""JWT session token 測試 (app.security.tokens)。

- 純邏輯 (缺 secret 時 create 丟 RuntimeError) 不需 PyJWT。
- 需要實際 encode/decode round-trip 的測試以 importorskip("jwt") 守護。
- decode_session_token 永不丟例外,壞 token / 過期 / 垃圾一律回 None。
"""

import importlib.util

import pytest

from app.security.tokens import create_session_token, decode_session_token

HAS_JWT = importlib.util.find_spec("jwt") is not None
requires_jwt = pytest.mark.skipif(not HAS_JWT, reason="PyJWT 未安裝")


# --- 純邏輯: 缺 secret 時 create 丟 RuntimeError (不需 PyJWT) ---

def test_create_without_secret_raises(monkeypatch):
    monkeypatch.delenv("SESSION_JWT_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_session_token("user_1", "admin", None)


def test_create_falls_back_to_admin_api_key(monkeypatch):
    """SESSION_JWT_SECRET 未設時改用 ADMIN_API_KEY,不丟例外。"""
    monkeypatch.delenv("SESSION_JWT_SECRET", raising=False)
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    token = create_session_token("user_1", "admin", None)
    assert isinstance(token, str) and token


# --- decode 永不丟例外 (不需 PyJWT) ---

@pytest.mark.parametrize("garbage", ["", "not.a.jwt", "abc", "x.y.z"])
def test_decode_garbage_returns_none(monkeypatch, garbage):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    assert decode_session_token(garbage) is None


# --- round-trip / 篡改 / 過期 (需 PyJWT) ---

@requires_jwt
def test_round_trip_returns_claims(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    token = create_session_token("user_1", "user", "jti")
    claims = decode_session_token(token)
    assert claims is not None
    assert claims["sub"] == "user_1"
    assert claims["role"] == "user"
    assert claims["app"] == "jti"
    assert "iat" in claims
    assert "exp" in claims


@requires_jwt
def test_app_none_round_trips(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    token = create_session_token("u", "admin", None)
    claims = decode_session_token(token)
    assert claims is not None
    assert claims["app"] is None


@requires_jwt
def test_tampered_token_returns_none(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    token = create_session_token("user_1", "admin", None)
    # 竄改 payload 段 (中間段) 必定使簽章失效。
    # 不可只翻最後一字元:base64url 末字元僅帶少數有效 bit,
    # 換字有機率解碼出相同 bytes,導致簽章仍有效 → 測試 flaky。
    header, payload, signature = token.split(".")
    flipped = "B" if payload[0] != "B" else "C"
    tampered = f"{header}.{flipped}{payload[1:]}.{signature}"
    assert decode_session_token(tampered) is None


@requires_jwt
def test_wrong_secret_returns_none(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "secret-one")
    token = create_session_token("user_1", "admin", None)
    monkeypatch.setenv("SESSION_JWT_SECRET", "secret-two")
    assert decode_session_token(token) is None


@requires_jwt
def test_expired_token_returns_none(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    token = create_session_token("user_1", "admin", None, expires_in=-10)
    assert decode_session_token(token) is None
