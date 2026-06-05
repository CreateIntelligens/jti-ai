"""
API 認證模組

認證優先順序：
1. session JWT（Authorization / API-Token / query / cookie）
2. token = ADMIN_API_KEY → super_admin
3. token = sk-xxx（MongoDB api_keys）→ 一般用戶，綁定 store
4. 無 token 或 token 無效 → 401
"""

import os

from fastapi import Depends, HTTPException, Request

from app.security.tokens import decode_session_token

ADMIN_ROLES = {"admin", "super_admin"}
KB_ACCESS_DENIED_DETAIL = "Insufficient permission for this knowledge base"


def _extract_bearer_token(request: Request) -> str | None:
    """從 Authorization header 提取 Bearer token"""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _extract_api_token(request: Request) -> str | None:
    """從 API-Token header 或 query parameter (token) 提取 token"""
    # Backward compatibility: API-Key
    token = request.headers.get("api-token") or request.headers.get("api-key")
    if not token:
        token = request.query_params.get("token")
    return token


def extract_user_gemini_api_key(request: Request) -> str | None:
    """從獨立 header 提取使用者自己的 Gemini API key。"""
    api_key = (request.headers.get("x-gemini-api-key") or "").strip()
    return api_key or None


def _extract_session_cookie(request: Request) -> str | None:
    cookies = getattr(request, "cookies", None)
    if not cookies:
        return None
    return cookies.get("session")


def _resolve_session_jwt(token: str) -> dict | None:
    """若 token 是有效的 session JWT,回傳該使用者的 auth dict;否則回 None。

    優先序最高 (在 ADMIN_API_KEY / sk-xxx 之前嘗試)。流程:
    1. decode_session_token 失敗 (None) → 回 None,讓後續分支處理。
    2. 解出 claims 後,若 deps.user_manager 可用則查使用者:
       - 不存在 → 401 (token 指向已刪除帳號)。
       - disabled → 401。
       - 否則以 user 的 role/scope/store_name 為準 (DB 為單一事實來源)。
    3. user_manager 不可用 (測試環境 / 尚未初始化) → 直接信任 claims。

    回傳的 dict 比既有 sk-xxx 分支多帶 scope / user_id 等欄位。
    """
    claims = decode_session_token(token)
    if not claims:
        return None

    user_id = claims.get("sub")
    role = claims.get("role")
    scope = claims.get("scope", claims.get("app"))
    store_name = None

    from app import deps

    if deps.user_manager is not None:
        user = deps.user_manager.get_user(user_id) if user_id else None
        if user is None:
            raise HTTPException(status_code=401, detail="Session user not found")
        if getattr(user, "disabled", False):
            raise HTTPException(status_code=401, detail="User is disabled")
        role = user.role
        scope = user.scope
        store_name = user.store_name

    return {
        "role": role,
        "scope": scope,
        "store_name": store_name,
        "user_id": user_id,
    }


def verify_auth(request: Request) -> dict:
    """
    驗證 API 請求

    優先序:
    1. token 為有效 session JWT → 該使用者 auth dict (含 scope/user_id)。
    2. token == ADMIN_API_KEY → super_admin。
    3. token == sk-xxx → 一般 user，綁定 store (形狀不變)。
    4. 無 token → 401。

    Returns:
        {"role": "super_admin", "store_name": None}  # ADMIN_API_KEY
        {"role": "user", "store_name": "...", "prompt_index": ...}  # sk-xxx key
        {"role": ..., "scope": ..., "store_name": ..., "user_id": ...}  # session JWT
    """
    token = (
        _extract_bearer_token(request)
        or _extract_api_token(request)
        or _extract_session_cookie(request)
    )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing session token or authorization credentials",
        )

    # 是 session JWT？(優先序最高;sk-xxx 不會 decode 成功,順序安全)
    jwt_auth = _resolve_session_jwt(token)
    if jwt_auth is not None:
        return jwt_auth

    # 是 Admin Key？→ super_admin
    admin_key = os.getenv("ADMIN_API_KEY")
    if admin_key and token == admin_key:
        return {"role": "super_admin", "store_name": None}

    # 是一般 Key？（查 MongoDB）
    from app import deps

    if deps.api_key_manager:
        api_key_info = deps.api_key_manager.verify_key(token)
        if api_key_info:
            return {
                "role": "user",
                "store_name": api_key_info.store_name,
                "prompt_index": api_key_info.prompt_index,
            }

    raise HTTPException(status_code=401, detail="Invalid API token")


def require_admin(auth_info: dict) -> None:
    """檢查是否為 admin 權限。

    向後兼容:接受既有 admin 與新的 super_admin。
    """
    if auth_info.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")


def can_access_kb(auth_info: dict, app: str) -> bool:
    """Return whether auth_info may manage the app knowledge workspace."""
    role = auth_info.get("role")
    if role in ADMIN_ROLES:
        return True
    if role == "user":
        return auth_info.get("scope") == app
    return False


def require_kb_access(app: str):
    """產生知識庫 workspace dependency。

    super_admin/admin 可跨 app;role=user 只能管理同 scope 的 app 知識庫。
    """

    def checker(auth: dict = Depends(verify_auth)) -> dict:
        if not can_access_kb(auth, app):
            raise HTTPException(
                status_code=403,
                detail=KB_ACCESS_DENIED_DETAIL,
            )
        return auth

    return checker


def require_role(*allowed: str):
    """產生一個 FastAPI dependency,要求 verify_auth 的 role 在 allowed 內。

    角色映射:
    - ADMIN_API_KEY → "super_admin"。
    - session JWT / sk-xxx → claims / DB 中的 role。

    因此 require_role("super_admin") 給真正的 super_admin (ADMIN_API_KEY 或
    DB 中 role=super_admin 的 JWT) 用。
    若要同時涵蓋兩者,明確列出: require_role("admin", "super_admin")。
    """

    def checker(request: Request) -> dict:
        auth = verify_auth(request)
        if auth.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return auth

    return checker


def verify_admin(request: Request) -> dict:
    """驗證請求並要求 admin 權限。"""
    auth_info = verify_auth(request)
    require_admin(auth_info)
    return auth_info


def verify_authenticated(request: Request) -> dict:
    """驗證已登入使用者,不限制 role。"""
    return verify_auth(request)
