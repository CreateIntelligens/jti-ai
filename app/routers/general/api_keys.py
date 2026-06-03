"""
API Key Management Endpoints
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.auth import verify_auth
import app.deps as deps

router = APIRouter(prefix="/api", tags=["API Key Management"])

ADMIN_ROLES = {"admin", "super_admin"}


def _is_admin(auth: dict) -> bool:
    return auth.get("role") in ADMIN_ROLES


def _require_admin(auth: dict) -> None:
    if not _is_admin(auth):
        raise HTTPException(status_code=403, detail="Admin access required")


def _api_key_manager():
    if not deps.api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")
    return deps.api_key_manager


def _public_key_payload(key) -> dict:
    return {
        "id": key.id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "store_name": key.store_name,
        "prompt_index": key.prompt_index,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at
    }


def _get_existing_key(manager, key_id: str):
    key = manager.get_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    return key


def _visible_store_names(auth: dict, request: Request) -> Optional[set[str]]:
    """回傳此 auth 能看到的 store name 集合。

    - admin / super_admin → None (代表「不限,全部可見」)。
    - 一般 user → 沿用 stores 面板的可見範圍邏輯 (scope→store),
      回傳該 user 能看到的 store name 集合;算不出來時回空集合。

    歸屬靠 store (而非另設 owner 欄位),與知識庫面板的權限一致。
    """
    if _is_admin(auth):
        return None

    # 重用 stores.py 既有的「user 可見 store」邏輯,避免另立一套真相來源。
    from app.routers.general.stores import _list_user_scoped_stores, _owner_key_hash

    try:
        payloads = _list_user_scoped_stores(auth, _owner_key_hash(request), None)
    except HTTPException:
        return set()
    return {name for p in payloads if (name := p.get("name"))}


def _require_key_in_scope(auth: dict, key, request: Request) -> None:
    """非 admin 只能操作「自己可見 store 清單」底下的 key。

    key 為 APIKey 物件 (已確認存在)。admin/super_admin 一律放行。
    """
    visible = _visible_store_names(auth, request)
    if visible is None:  # admin
        return
    if key.store_name not in visible:
        # 不洩漏「key 是否存在」,一律回 404
        raise HTTPException(status_code=404, detail="API Key 不存在")


class CreateAPIKeyRequest(BaseModel):
    name: str  # 用途說明
    store_name: str  # 綁定的知識庫
    prompt_index: Optional[int] = None  # 可選指定 prompt


class UpdateAPIKeyRequest(BaseModel):
    name: Optional[str] = None
    prompt_index: Optional[int] = None


@router.get("/keys")
def list_api_keys(
    request: Request,
    store_name: Optional[str] = None,
    auth: dict = Depends(verify_auth),
):
    """列出 API Keys。

    - admin / super_admin: 全部,可選 store_name 篩選。
    - 一般 user: 只列自己可見 store 清單 (scope→store) 底下的 key。
    """
    manager = _api_key_manager()
    visible = _visible_store_names(auth, request)

    if visible is None:  # admin
        keys = manager.list_keys(store_name)
    else:
        if not visible:
            return []
        # user 忽略傳入的 store_name,只回可見 store 的 key
        keys = [k for k in manager.list_keys() if k.store_name in visible]

    # 不返回 key_hash / key_encrypted
    return [_public_key_payload(k) for k in keys]


@router.post("/keys")
def create_api_key(request: CreateAPIKeyRequest, auth: dict = Depends(verify_auth)):
    """建立新的 API Key（僅 admin / super_admin）。

    一般 user 無簽發權限;金鑰一律由 admin 指派給特定知識庫 (store)。
    """
    _require_admin(auth)
    manager = _api_key_manager()

    api_key, raw_key = manager.create_key(
        name=request.name,
        store_name=request.store_name,
        prompt_index=request.prompt_index
    )

    return {
        "id": api_key.id,
        "key": raw_key,  # 只有這一次會顯示完整 key
        "key_prefix": api_key.key_prefix,
        "name": api_key.name,
        "store_name": api_key.store_name,
        "prompt_index": api_key.prompt_index,
        "message": "請妥善保存此 API Key"
    }


@router.get("/keys/{key_id}")
def get_api_key(key_id: str, request: Request, auth: dict = Depends(verify_auth)):
    """取得 API Key 資訊（admin 全部 / user 限自己可見 store）"""
    manager = _api_key_manager()
    key = _get_existing_key(manager, key_id)
    _require_key_in_scope(auth, key, request)

    return _public_key_payload(key)


@router.get("/keys/{key_id}/reveal")
def reveal_api_key(key_id: str, request: Request, auth: dict = Depends(verify_auth)):
    """還原並回傳完整明文金鑰（admin 全部 / user 限自己可見 store）。

    前端在使用者點「眼睛」並二次確認後才呼叫。沿用既有 session 驗證
    與可見範圍檢查,不另外要求重新輸入密碼。
    """
    manager = _api_key_manager()
    key = _get_existing_key(manager, key_id)
    _require_key_in_scope(auth, key, request)

    try:
        raw_key = manager.reveal_key(key_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if raw_key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"id": key.id, "key": raw_key}


@router.put("/keys/{key_id}")
def update_api_key(key_id: str, request: UpdateAPIKeyRequest, auth: dict = Depends(verify_auth)):
    """更新 API Key 設定（僅 admin / super_admin）"""
    _require_admin(auth)
    manager = _api_key_manager()

    key = manager.update_key(
        key_id=key_id,
        name=request.name,
        prompt_index=request.prompt_index
    )

    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {
        "id": key.id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "store_name": key.store_name,
        "prompt_index": key.prompt_index
    }


@router.delete("/keys/{key_id}")
def delete_api_key(key_id: str, auth: dict = Depends(verify_auth)):
    """刪除 API Key（僅 admin / super_admin）"""
    _require_admin(auth)
    manager = _api_key_manager()

    success = manager.delete_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"message": "API Key 已刪除"}
