"""JWT session token 工具 (HS256, PyJWT)。

- create_session_token: 簽發含 sub/role/app/iat/exp 的 session token。
- decode_session_token: 驗證並回傳 claims;任何失敗 (壞簽章 / 過期 / 格式錯) 一律回 None,絕不丟例外給呼叫端。

secret 來源優先序:
1. 環境變數 SESSION_JWT_SECRET
2. 環境變數 ADMIN_API_KEY (fallback)
兩者皆未設時,簽發 token 會丟 RuntimeError——絕不 hardcode 預設 secret (安全漏洞)。
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


def _get_secret() -> str | None:
    """取得簽章 secret;SESSION_JWT_SECRET 優先,否則 fallback 到 ADMIN_API_KEY。"""
    return os.getenv("SESSION_JWT_SECRET") or os.getenv("ADMIN_API_KEY")


def create_session_token(
    user_id: str,
    role: str,
    app: str | None,
    *,
    expires_in: int = 86400,
) -> str:
    """簽發 HS256 session token。

    claims: sub=user_id, role, app, iat, exp。

    Raises:
        RuntimeError: 找不到任何可用 secret 時 (絕不退回 hardcode 預設值)。
    """
    secret = _get_secret()
    if not secret:
        raise RuntimeError(
            "缺少 session 簽章 secret: 請設定 SESSION_JWT_SECRET 或 ADMIN_API_KEY"
        )

    import jwt

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "app": app,
        "iat": now,
        "exp": now.timestamp() + expires_in,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict | None:
    """驗證並解出 claims;valid & 未過期回 dict,任何失敗回 None (絕不丟例外)。"""
    if not token:
        return None

    secret = _get_secret()
    if not secret:
        return None

    try:
        import jwt

        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except Exception as exc:  # noqa: BLE001 — 任何失敗一律回 None
        logger.debug("[decode_session_token] 解碼失敗: %s", exc)
        return None
