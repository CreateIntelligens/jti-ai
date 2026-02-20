"""
Store Management API Endpoints
"""

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


@router.get("/stores")
def list_stores(auth: dict = Depends(verify_auth)):
    """列出所有 Store。（Admin only）"""
    require_admin(auth)
    mgr = _get_or_create_manager()
    stores = mgr.list_stores()
    return [{"name": s.name, "display_name": s.display_name} for s in stores]


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
