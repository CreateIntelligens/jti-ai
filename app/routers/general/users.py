"""帳號管理 REST API (CRUD over users)。

三層 RBAC 授權:
- 所有端點至少需 admin (require_role("admin", "super_admin"))。
- admin 僅能操作 role=="user" 的對象 (建立 / 停用 / 刪除)。
- super_admin 可操作任何人,但不可停用 / 刪除自己。

回應一律省略 password_hash。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

import app.deps as deps
from app.auth import require_role
from app.users import User

router = APIRouter(prefix="/api", tags=["User Management"])

# module-level 守門依賴 (固定可被測試以 dependency_overrides 覆寫)
require_admin_dep = require_role("admin", "super_admin")


class UserOut(BaseModel):
    """對外使用者表示,省略 password_hash。"""
    id: str
    username: str
    role: str
    scope: str | None = None
    store_name: str | None = None
    created_by: str | None = None
    created_at: str
    disabled: bool

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            scope=user.scope,
            store_name=user.store_name,
            created_by=user.created_by,
            created_at=user.created_at,
            disabled=user.disabled,
        )


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    scope: str | None = None
    store_name: str | None = None


class SetDisabledRequest(BaseModel):
    disabled: bool


def _require_manager():
    """取得 user_manager,未初始化則 500。"""
    if deps.user_manager is None:
        raise HTTPException(status_code=500, detail="User Manager 未初始化")
    return deps.user_manager


def _get_target_or_404(manager, user_id: str) -> User:
    target = manager.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="使用者不存在")
    return target


def _assert_can_target(auth: dict, target: User) -> None:
    """檢查呼叫者是否有權操作 target (停用 / 刪除)。

    - admin: 僅能操作 role=="user"。
    - super_admin: 任何人,但不可操作自己。
    """
    role = auth.get("role")
    if role == "super_admin":
        if target.id == auth.get("user_id"):
            raise HTTPException(status_code=400, detail="cannot disable self")
        return
    # admin
    if target.role != "user":
        raise HTTPException(status_code=403, detail="admin 僅能操作一般使用者")


@router.get("/users", response_model=list[UserOut])
def list_users(
    role: str | None = None,
    scope: str | None = None,
    auth: dict = Depends(require_admin_dep),
):
    """列出使用者,可選 role / scope 篩選。"""
    manager = _require_manager()
    return [UserOut.from_user(u) for u in manager.list_users(role=role, scope=scope)]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(request: CreateUserRequest, auth: dict = Depends(require_admin_dep)):
    """建立使用者。

    - admin 僅能建立 role=="user";其他角色 → 403。
    - super_admin 可建立任何角色。
    """
    manager = _require_manager()

    caller_role = auth.get("role")
    if caller_role == "admin" and request.role != "user":
        raise HTTPException(status_code=403, detail="admin 僅能建立一般使用者")

    try:
        user = manager.create_user(
            username=request.username,
            password=request.password,
            role=request.role,
            scope=request.scope,
            store_name=request.store_name,
            created_by=auth.get("user_id"),
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="使用者名稱已存在") from exc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return UserOut.from_user(user)


@router.patch("/users/{user_id}/disabled", response_model=UserOut)
def set_user_disabled(
    user_id: str,
    request: SetDisabledRequest,
    auth: dict = Depends(require_admin_dep),
):
    """啟用 / 停用使用者。"""
    manager = _require_manager()
    target = _get_target_or_404(manager, user_id)
    _assert_can_target(auth, target)

    manager.set_disabled(user_id, request.disabled)
    updated = _get_target_or_404(manager, user_id)
    return UserOut.from_user(updated)


@router.delete("/users/{user_id}")
def delete_user(user_id: str, auth: dict = Depends(require_admin_dep)):
    """刪除使用者。"""
    manager = _require_manager()
    target = _get_target_or_404(manager, user_id)
    _assert_can_target(auth, target)

    success = manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="使用者不存在")
    return {"message": "使用者已刪除"}
