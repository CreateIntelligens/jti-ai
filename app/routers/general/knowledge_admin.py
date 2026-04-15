"""
Knowledge Management API for JTI and HCIoT.
"""

import logging
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import verify_admin, verify_auth
from app.routers.knowledge_utils import (
    delete_from_rag,
    extract_docx_text,
    sync_to_rag,
    write_docx_text,
)
from app.services.knowledge_store import get_knowledge_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Management"], dependencies=[Depends(verify_admin)])

EDITABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".docx"}
TEXT_PREVIEW_EXTENSIONS = EDITABLE_EXTENSIONS | {".log", ".py", ".js", ".html"}
SUPPORTED_APPS = {"jti", "hciot"}


def _normalize_app_name(app_name: str) -> str:
    normalized = (app_name or "").strip().lower()
    if normalized not in SUPPORTED_APPS:
        raise HTTPException(status_code=400, detail="Unsupported app. Use 'jti' or 'hciot'.")
    return normalized


def _safe_filename(name: str) -> str:
    return Path(name).name




class UpdateContentRequest(BaseModel):
    content: str


@router.get("/files/")
def list_knowledge_files(
    app_name: str = Query(..., alias="app"),
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    namespace = _normalize_app_name(app_name)
    store = get_knowledge_store()
    files = store.list_files(language, namespace=namespace)
    return {"files": files, "language": language, "app": namespace}


@router.get("/files/{filename}/content")
def get_file_content(
    filename: str,
    app_name: str = Query(..., alias="app"),
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    namespace = _normalize_app_name(app_name)
    safe_name = _safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name, namespace=namespace)
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
            "app": namespace,
        }

    if ext not in TEXT_PREVIEW_EXTENSIONS:
        return {
            "filename": safe_name,
            "editable": False,
            "content": None,
            "message": "此檔案格式不支援線上預覽，請下載查看",
            "app": namespace,
        }

    return {
        "filename": safe_name,
        "editable": True,
        "content": file_bytes.decode("utf-8", errors="replace"),
        "size": doc.get("size", len(file_bytes)),
        "app": namespace,
    }


@router.get("/files/{filename}/download")
def download_file(
    filename: str,
    app_name: str = Query(..., alias="app"),
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    namespace = _normalize_app_name(app_name)
    safe_name = _safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name, namespace=namespace)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    file_bytes = doc.get("data", b"")
    content_type = doc.get("content_type") or "application/octet-stream"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"}
    return Response(content=file_bytes, media_type=content_type, headers=headers)


@router.put("/files/{filename}/content")
async def update_file_content(
    filename: str,
    req: UpdateContentRequest,
    app_name: str = Query(..., alias="app"),
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    namespace = _normalize_app_name(app_name)
    safe_name = _safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

    store = get_knowledge_store()
    doc = store.get_file(language, safe_name, namespace=namespace)
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

    updated = store.update_file_content(language, safe_name, new_bytes, namespace=namespace)
    if not updated:
        raise HTTPException(status_code=404, detail="檔案不存在")

    try:
        sync_to_rag(namespace, language, safe_name, new_bytes)
    except Exception as e:
        return {"message": f"已更新，但 RAG 同步失敗: {e}", "synced": False, "app": namespace}

    return {"message": "已更新", "synced": True, "app": namespace}


@router.post("/upload/")
async def upload_knowledge_file(
    app_name: str = Query(..., alias="app"),
    language: str = "zh",
    file: UploadFile = File(...),
    auth: dict = Depends(verify_auth),
):
    namespace = _normalize_app_name(app_name)
    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = _safe_filename(display_name)
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
        namespace=namespace,
    )

    rag_synced = False
    try:
        sync_to_rag(namespace, language, saved["name"], file_bytes)
        rag_synced = True
    except Exception as e:
        logger.warning("[Knowledge] RAG sync failed for %s/%s: %s", namespace, saved["name"], e)

    return {
        "name": saved["name"],
        "display_name": saved["display_name"],
        "size": saved["size"],
        "synced": rag_synced,
        "app": namespace,
    }


@router.delete("/files/{filename}")
def delete_knowledge_file(
    filename: str,
    app_name: str = Query(..., alias="app"),
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    namespace = _normalize_app_name(app_name)
    safe_name = _safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name, namespace=namespace)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    try:
        delete_from_rag(namespace, language, safe_name)
    except Exception as e:
        logger.warning("[Knowledge] RAG delete failed for %s/%s: %s", namespace, safe_name, e)
        raise HTTPException(status_code=502, detail="RAG 同步刪除失敗，Mongo 未刪除")

    deleted = store.delete_file(language, safe_name, namespace=namespace)
    if not deleted:
        raise HTTPException(status_code=404, detail="檔案不存在")

    return {
        "message": "已刪除",
        "app": namespace,
        "synced": True,
        "mongo_deleted": True,
    }
