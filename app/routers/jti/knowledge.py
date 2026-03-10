"""
JTI 知識庫管理 API

MongoDB + Gemini File Search Store 同步管理。
"""

import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from urllib.parse import quote

from app.auth import verify_admin, verify_auth
from app.routers.knowledge_utils import (
    EDITABLE_EXTENSIONS,
    TEXT_PREVIEW_EXTENSIONS,
    delete_from_gemini,
    extract_docx_text,
    get_store_name,
    safe_filename,
    start_background_sync,
    sync_to_gemini,
    write_docx_text,
)
from app.services.knowledge_store import get_knowledge_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["JTI Knowledge"], dependencies=[Depends(verify_admin)])

ENV_PREFIX = "JTI"
FALLBACK_ENV_KEY = "JTI_STORE_ID_ZH"
LOG_PREFIX = "JTI sync"


def _store_name(language: str) -> str | None:
    return get_store_name(ENV_PREFIX, language, fallback_env_key=FALLBACK_ENV_KEY)


# ========== 列出檔案 ==========


@router.get("/files/")
def list_knowledge_files(language: str = "zh", auth: dict = Depends(verify_auth)):
    """列出知識庫中的檔案"""
    store = get_knowledge_store()
    files = store.list_files(language)
    start_background_sync(
        ENV_PREFIX, get_knowledge_store, language, LOG_PREFIX,
        insert_kwargs={"namespace": "jti"}, fallback_env_key=FALLBACK_ENV_KEY,
    )
    return {"files": files, "language": language}


# ========== 讀取檔案內容 ==========


@router.get("/files/{filename}/content")
def get_file_content(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """讀取檔案內容（僅支援文字檔）"""
    safe_name = safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    ext = Path(safe_name).suffix.lower()
    file_bytes = doc.get("data", b"")

    if ext == ".docx":
        content = extract_docx_text(file_bytes)
        return {
            "filename": safe_name,
            "editable": True,
            "content": content,
            "size": doc.get("size", len(file_bytes)),
        }

    if ext not in TEXT_PREVIEW_EXTENSIONS:
        return {
            "filename": safe_name,
            "editable": False,
            "content": None,
            "message": "此檔案格式不支援線上預覽，請下載查看",
        }

    content = file_bytes.decode("utf-8", errors="replace")
    return {
        "filename": safe_name,
        "editable": True,
        "content": content,
        "size": doc.get("size", len(file_bytes)),
    }


# ========== 下載檔案 ==========


@router.get("/files/{filename}/download")
def download_file(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """下載知識庫檔案"""
    safe_name = safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    file_bytes = doc.get("data", b"")
    content_type = doc.get("content_type") or "application/octet-stream"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"
    }
    return Response(content=file_bytes, media_type=content_type, headers=headers)


# ========== 更新檔案內容 ==========


class UpdateContentRequest(BaseModel):
    content: str


@router.put("/files/{filename}/content")
async def update_file_content(
    filename: str,
    req: UpdateContentRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    """更新文字檔內容（同步到 Gemini File Search）"""
    safe_name = safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

    store = get_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    old_bytes = doc.get("data", b"")
    if ext == ".docx":
        try:
            new_bytes = write_docx_text(old_bytes, req.content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {e}")
    else:
        new_bytes = req.content.encode("utf-8")

    updated = store.update_file_content(language, safe_name, new_bytes)
    if not updated:
        raise HTTPException(status_code=404, detail="檔案不存在")

    store_name = _store_name(language)
    if store_name:
        try:
            sync_to_gemini(store_name, safe_name, new_bytes)
        except Exception as e:
            return {"message": f"已更新，但 Gemini 同步失敗: {e}", "synced": False}

    return {"message": "已更新", "synced": True}


# ========== 上傳檔案 ==========


@router.post("/upload/")
async def upload_knowledge_file(
    language: str = "zh",
    file: UploadFile = File(...),
    auth: dict = Depends(verify_auth),
):
    """上傳檔案到知識庫 + Gemini File Search"""
    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = safe_filename(display_name)
    file_bytes = await file.read()

    ext = Path(safe_name).suffix.lower()
    editable = ext in EDITABLE_EXTENSIONS
    content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    store = get_knowledge_store()
    saved = store.insert_file(
        language=language,
        filename=safe_name,
        data=file_bytes,
        display_name=safe_name,
        content_type=content_type,
        editable=editable,
    )

    gemini_synced = False
    store_name = _store_name(language)
    if store_name:
        try:
            gemini_synced = sync_to_gemini(store_name, saved["name"], file_bytes)
        except Exception as e:
            logger.warning(f"[KB] Gemini sync failed for {saved['name']}: {e}")

    return {
        "name": saved["name"],
        "display_name": saved["display_name"],
        "size": saved["size"],
        "synced": gemini_synced,
    }


# ========== 刪除檔案 ==========


@router.delete("/files/{filename}")
def delete_knowledge_file(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """刪除檔案 + Gemini File Search 中的對應文件"""
    safe_name = safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    store_name = _store_name(language)
    gemini_deleted_count = 0
    if store_name:
        try:
            gemini_deleted_count = delete_from_gemini(store_name, safe_name)
        except Exception as e:
            logger.warning(f"[KB] Gemini delete failed for {safe_name}: {e}")
            raise HTTPException(status_code=502, detail="Gemini 同步刪除失敗，Mongo 未刪除")

    deleted = store.delete_file(language, safe_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="檔案不存在")
    return {
        "message": "已刪除",
        "synced": True,
        "mongo_deleted": True,
        "gemini_deleted_count": gemini_deleted_count,
    }
