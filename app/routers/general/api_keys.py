"""
API Key Management Endpoints
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import verify_auth, require_admin
import app.deps as deps

router = APIRouter(prefix="/api", tags=["API Key Management"])


class CreateAPIKeyRequest(BaseModel):
    name: str  # 用途說明
    store_name: str  # 綁定的知識庫
    prompt_index: Optional[int] = None  # 可選指定 prompt


class UpdateAPIKeyRequest(BaseModel):
    name: Optional[str] = None
    prompt_index: Optional[int] = None


@router.get("/keys")
def list_api_keys(store_name: Optional[str] = None, auth: dict = Depends(verify_auth)):
    """列出 API Keys，可選篩選特定知識庫（Admin only）"""
    require_admin(auth)
    if not deps.api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    keys = deps.api_key_manager.list_keys(store_name)
    # 不返回 key_hash
    return [
        {
            "id": k.id,
            "key_prefix": k.key_prefix,
            "name": k.name,
            "store_name": k.store_name,
            "prompt_index": k.prompt_index,
            "created_at": k.created_at,
            "last_used_at": k.last_used_at
        }
        for k in keys
    ]


@router.post("/keys")
def create_api_key(request: CreateAPIKeyRequest, auth: dict = Depends(verify_auth)):
    """建立新的 API Key（Admin only）"""
    require_admin(auth)
    if not deps.api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    api_key, raw_key = deps.api_key_manager.create_key(
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
        "message": "請妥善保存此 API Key，之後無法再次查看完整金鑰"
    }


@router.get("/keys/{key_id}")
def get_api_key(key_id: str, auth: dict = Depends(verify_auth)):
    """取得 API Key 資訊（Admin only）"""
    require_admin(auth)
    if not deps.api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    key = deps.api_key_manager.get_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {
        "id": key.id,
        "key_prefix": key.key_prefix,
        "name": key.name,
        "store_name": key.store_name,
        "prompt_index": key.prompt_index,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at
    }


@router.put("/keys/{key_id}")
def update_api_key(key_id: str, request: UpdateAPIKeyRequest, auth: dict = Depends(verify_auth)):
    """更新 API Key 設定（Admin only）"""
    require_admin(auth)
    if not deps.api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    key = deps.api_key_manager.update_key(
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
    """刪除 API Key（Admin only）"""
    require_admin(auth)
    if not deps.api_key_manager:
        raise HTTPException(status_code=500, detail="API Key Manager 未初始化")

    success = deps.api_key_manager.delete_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"message": "API Key 已刪除"}
