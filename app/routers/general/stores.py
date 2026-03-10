"""
Store Management API Endpoints
"""

import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import verify_auth, require_admin, extract_user_gemini_api_key
from app.deps import _get_or_create_manager
from app.services.gemini_clients import (
    get_client_by_index, get_key_count, get_key_names, get_store_key_index, register_store,
)

router = APIRouter(prefix="/api", tags=["Store Management"])


class CreateStoreRequest(BaseModel):
    display_name: str
    key_index: int = 0  # 0-based，對應 GEMINI_API_KEYS 的第幾把 key


class QueryRequest(BaseModel):
    store_name: str
    question: str


def _normalize_store_name(store_name: str | None) -> str | None:
    if not store_name:
        return None
    return store_name if store_name.startswith("fileSearchStores/") else f"fileSearchStores/{store_name}"


def _resolve_managed_store_context(store_name: str) -> dict[str, str] | None:
    normalized = _normalize_store_name(store_name)
    if not normalized:
        return None

    mappings = [
        ("jti", "zh", os.getenv("JTI_STORE_ID_ZH")),
        ("jti", "en", os.getenv("JTI_STORE_ID_EN")),
        ("hciot", "zh", os.getenv("HCIOT_STORE_ID_ZH") or os.getenv("HCIOT_STORE_ID")),
        ("hciot", "en", os.getenv("HCIOT_STORE_ID_EN")),
    ]

    for app_name, language, configured_store in mappings:
        if normalized == _normalize_store_name(configured_store):
            return {"managed_app": app_name, "managed_language": language}
    return None


@router.get("/stores")
def list_stores(request: Request, auth: dict = Depends(verify_auth)):
    """列出所有 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager(user_api_key=extract_user_gemini_api_key(request))
    stores = mgr.list_stores()
    result = []
    for store in stores:
        managed_context = _resolve_managed_store_context(store.name) or {}
        result.append({
            "name": store.name,
            "display_name": store.display_name,
            "managed_app": managed_context.get("managed_app"),
            "managed_language": managed_context.get("managed_language"),
            "key_index": get_store_key_index(store.name),
        })
    return result


@router.get("/keys/count")
def get_keys_count(auth: dict = Depends(verify_auth)):
    """回傳目前已設定的 Gemini API key 數量與名稱。（Admin only）"""
    require_admin(auth)
    names = get_key_names()
    return {"count": get_key_count(), "names": names}


@router.post("/stores")
def create_store(req: CreateStoreRequest, request: Request, auth: dict = Depends(verify_auth)):
    """建立新 Store。"""
    require_admin(auth)
    user_api_key = extract_user_gemini_api_key(request)

    if user_api_key:
        # 使用者自帶 key → 建在使用者自己的 key 下，不影響系統 registry
        mgr = _get_or_create_manager(user_api_key=user_api_key)
        store_name = mgr.create_store(req.display_name)
        return {"name": store_name}
    else:
        # 系統 admin → 用 key_index 指定的系統 key 建立
        client = get_client_by_index(req.key_index)
        store = client.file_search_stores.create(config={"display_name": req.display_name})
        # 把新 store 註冊到 registry（讓後續操作用對的 key）
        register_store(store.name, client)
        return {"name": store.name}


@router.get("/stores/{store_name:path}/files")
def list_files(store_name: str, request: Request, auth: dict = Depends(verify_auth)):
    """列出 Store 中的檔案。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager(user_api_key=extract_user_gemini_api_key(request))
    files = mgr.list_files(store_name)
    return [{"name": f.name, "display_name": f.display_name} for f in files]


@router.post("/query")
def query(req: QueryRequest, request: Request, auth: dict = Depends(verify_auth)):
    """查詢 Store (單次)。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager(user_api_key=extract_user_gemini_api_key(request))
    response = mgr.query(req.store_name, req.question)
    return {"answer": response.text}


@router.delete("/stores/{store_name:path}")
def delete_store(store_name: str, request: Request, auth: dict = Depends(verify_auth)):
    """刪除 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager(user_api_key=extract_user_gemini_api_key(request))
    mgr.delete_store(store_name)
    return {"ok": True}
