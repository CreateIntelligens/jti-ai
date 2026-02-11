"""
API 認證模組

認證優先順序：
1. 來自前端（同 origin）→ 放行，視為 admin
2. Bearer token = ADMIN_API_KEY → admin
3. Bearer token = sk-xxx（MongoDB api_keys）→ 一般用戶，綁定 store
4. 無 token → 401
"""

import os
from urllib.parse import urlparse
from fastapi import HTTPException, Request


# 允許的內部 host（前端同 origin 判定用）
_INTERNAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def _extract_bearer_token(request: Request) -> str | None:
    """從 Authorization header 提取 Bearer token"""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _is_same_origin(request: Request) -> bool:
    """
    判斷請求是否來自前端（同 origin）

    瀏覽器發送的請求會帶 Origin 或 Referer header，
    如果 host 與 server 一致，視為前端請求。
    """
    # 取得 server host
    server_host = request.headers.get("host", "")
    server_hostname = server_host.split(":")[0] if server_host else ""

    # 檢查 Origin header
    origin = request.headers.get("origin", "")
    if origin:
        parsed = urlparse(origin)
        origin_host = parsed.hostname or ""
        if origin_host == server_hostname or origin_host in _INTERNAL_HOSTS:
            return True

    # 檢查 Referer header
    referer = request.headers.get("referer", "")
    if referer:
        parsed = urlparse(referer)
        referer_host = parsed.hostname or ""
        if referer_host == server_hostname or referer_host in _INTERNAL_HOSTS:
            return True

    return False


def verify_auth(request: Request) -> dict:
    """
    驗證 API 請求

    Returns:
        {"role": "admin", "store_name": None}  # admin 或前端
        {"role": "user", "store_name": "...", "prompt_index": ...}  # 一般 key
    """
    # 1. 來自前端（同 origin）→ 放行
    if _is_same_origin(request):
        return {"role": "admin", "store_name": None}

    # 2. 提取 Bearer token
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # 3. 是 Admin Key？
    admin_key = os.getenv("ADMIN_API_KEY")
    if admin_key and token == admin_key:
        return {"role": "admin", "store_name": None}

    # 4. 是一般 Key？（查 MongoDB）
    from app.api_keys import APIKeyManager
    from app.main import api_key_manager

    if api_key_manager:
        api_key_info = api_key_manager.verify_key(token)
        if api_key_info:
            return {
                "role": "user",
                "store_name": api_key_info.store_name,
                "prompt_index": api_key_info.prompt_index,
            }

    raise HTTPException(status_code=401, detail="Invalid API key")


def require_admin(auth_info: dict) -> None:
    """檢查是否為 admin 權限"""
    if auth_info.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
