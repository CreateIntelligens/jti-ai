"""
Store Management API Endpoints
"""

import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from pydantic import BaseModel

from app.auth import verify_auth, require_admin
from app.deps import _get_or_create_manager

router = APIRouter(prefix="/api", tags=["Store Management"])


class CreateStoreRequest(BaseModel):
    display_name: str


class QueryRequest(BaseModel):
    store_name: str
    question: str


def _normalize_store_name(store_name: str | None) -> str | None:
    if not store_name:
        return None
    return store_name if store_name.startswith("fileSearchStores/") else f"fileSearchStores/{store_name}"


def _resolve_managed_store_context(store_name: str) -> dict[str, str] | None:
    normalized = _normalize_store_name(store_name)
    mappings = [
        ("jti", "zh", os.getenv("JTI_STORE_ID_ZH")),
        ("jti", "en", os.getenv("JTI_STORE_ID_EN")),
        ("hciot", "zh", os.getenv("HCIOT_STORE_ID_ZH") or os.getenv("HCIOT_STORE_ID")),
        ("hciot", "en", os.getenv("HCIOT_STORE_ID_EN")),
    ]

    for app_name, language, configured_store in mappings:
        if normalized and normalized == _normalize_store_name(configured_store):
            return {"managed_app": app_name, "managed_language": language}
    return None


@router.get("/stores")
def list_stores(auth: dict = Depends(verify_auth)):
    """列出所有 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    stores = mgr.list_stores()
    result = []
    for store in stores:
        managed_context = _resolve_managed_store_context(store.name) or {}
        result.append({
            "name": store.name,
            "display_name": store.display_name,
            "managed_app": managed_context.get("managed_app"),
            "managed_language": managed_context.get("managed_language"),
        })
    return result


@router.post("/stores")
def create_store(req: CreateStoreRequest, auth: dict = Depends(verify_auth)):
    """建立新 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    store_name = mgr.create_store(req.display_name)
    return {"name": store_name}


@router.get("/stores/{store_name:path}/files")
def list_files(store_name: str, auth: dict = Depends(verify_auth)):
    """列出 Store 中的檔案。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    files = mgr.list_files(store_name)
    return [{"name": f.name, "display_name": f.display_name} for f in files]


@router.delete("/files/{file_name:path}")
def delete_file(file_name: str, auth: dict = Depends(verify_auth)):
    """刪除檔案。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    print(f"嘗試刪除檔案: {file_name}")
    mgr.delete_file(file_name)
    return {"ok": True}


@router.post("/stores/{store_name:path}/upload")
async def upload_file(store_name: str, file: UploadFile = File(...), auth: dict = Depends(verify_auth)):
    """上傳檔案到 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()

    temp_dir = Path("/tmp/gemini-upload")
    temp_dir.mkdir(exist_ok=True)
    ext = Path(file.filename).suffix if file.filename else ""
    safe_filename = f"{uuid.uuid4()}{ext}"
    temp_path = temp_dir / safe_filename

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = mgr.upload_file(
            store_name, str(temp_path), file.filename, mime_type=None
        )
        return {"name": result}
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/query")
def query(req: QueryRequest, auth: dict = Depends(verify_auth)):
    """查詢 Store (單次)。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    response = mgr.query(req.store_name, req.question)
    return {"answer": response.text}


@router.delete("/stores/{store_name:path}")
def delete_store(store_name: str, auth: dict = Depends(verify_auth)):
    """刪除 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    mgr.delete_store(store_name)
    return {"ok": True}
