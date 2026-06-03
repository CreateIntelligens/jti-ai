"""登入 / 登出 API (session JWT)。

- POST /api/auth/login: 驗證帳密,成功回 {token, role, scope} 並設 httpOnly cookie `session`;
  帳密錯一律 401 + 通用訊息 (不洩漏是帳號還是密碼錯)。
- POST /api/auth/logout: 清除 `session` cookie,回 {ok: true} (stateless JWT,登出即清 cookie)。

token 也一併放在 response body,讓非瀏覽器客戶端 (CLI / API) 也能取用。
"""

import logging

from fastapi import APIRouter, HTTPException, Response, Depends
from pydantic import BaseModel

import app.deps as deps
from app.security.tokens import create_session_token
from app.auth import verify_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# session cookie 名稱與有效期 (秒),與 token 預設一致
_COOKIE_NAME = "session"
_COOKIE_MAX_AGE = 86400

# 帳密錯誤一律回此通用訊息,絕不區分帳號 / 密碼。
_INVALID_CREDENTIALS = "Invalid credentials"


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    """驗證帳密,成功簽發 session token 並設 cookie。"""
    if not deps.user_manager:
        raise HTTPException(status_code=500, detail="User Manager 未初始化")

    user = deps.user_manager.verify_credentials(body.username, body.password)
    if not user:
        # 通用訊息,不洩漏帳號是否存在 / 密碼是否正確
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

    token = create_session_token(user.id, user.role, user.scope)

    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )

    return {"token": token, "role": user.role, "scope": user.scope}


@router.post("/logout")
def logout(response: Response):
    """清除 session cookie (stateless JWT,登出即清 cookie)。"""
    response.delete_cookie(key=_COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def get_me(auth: dict = Depends(verify_auth)):
    """獲取目前登入使用者的資訊。"""
    user_id = auth.get("user_id")
    username = None
    if user_id and deps.user_manager:
        user = deps.user_manager.get_user(user_id)
        if user:
            username = user.username

    return {
        "user_id": user_id,
        "username": username,
        "role": auth.get("role"),
        "scope": auth.get("scope"),
        "store_name": auth.get("store_name"),
    }
