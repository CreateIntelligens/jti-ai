"""
Homepage CMS knowledge management API for JTI and HCIoT.
"""

import io
import mimetypes
import os
import tempfile
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import verify_admin, verify_auth
from app.deps import _get_or_create_manager
from app.services.knowledge_store import get_knowledge_store

router = APIRouter(prefix="/api/admin/knowledge", tags=["CMS Knowledge"], dependencies=[Depends(verify_admin)])

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


def _get_store_name(app_name: str, language: str) -> str | None:
    normalized_app = _normalize_app_name(app_name)
    normalized_language = "en" if str(language).lower().startswith("en") else "zh"

    if normalized_app == "jti":
        env_key = f"GEMINI_FILE_SEARCH_STORE_ID_{normalized_language.upper()}"
        store_id = os.getenv(env_key) or os.getenv("GEMINI_FILE_SEARCH_STORE_ID")
    else:
        env_key = f"HCIOT_STORE_ID_{normalized_language.upper()}"
        store_id = os.getenv(env_key) or os.getenv("HCIOT_STORE_ID")

    if not store_id:
        return None
    return store_id if store_id.startswith("fileSearchStores/") else f"fileSearchStores/{store_id}"


def _extract_docx_text_from_bytes(data: bytes) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            xml_content = zf.read("word/document.xml")
        root = ET.fromstring(xml_content)
        paragraphs = []
        for p in root.iter(f"{ns}p"):
            texts = [t.text or "" for t in p.iter(f"{ns}t")]
            paragraphs.append("".join(texts))
        return "\n".join(paragraphs)
    except Exception as e:
        return f"[無法解析 docx: {e}]"


def _write_docx_text_to_bytes(original_data: bytes, text: str) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    with zipfile.ZipFile(io.BytesIO(original_data), "r") as zf:
        xml_content = zf.read("word/document.xml")

    root = ET.fromstring(xml_content)
    body = root.find(f"{{{ns}}}body")
    if body is None:
        raise ValueError("docx 格式異常：找不到 body")

    non_para = []
    for child in list(body):
        if child.tag == f"{{{ns}}}p":
            body.remove(child)
        else:
            non_para.append(child)
            body.remove(child)

    for line in text.split("\n"):
        p = ET.SubElement(body, f"{{{ns}}}p")
        r = ET.SubElement(p, f"{{{ns}}}r")
        t = ET.SubElement(r, f"{{{ns}}}t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = line

    for elem in non_para:
        body.append(elem)

    new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_data), "r") as z_in:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename == "word/document.xml":
                    z_out.writestr(item, new_xml)
                else:
                    z_out.writestr(item, z_in.read(item.filename))
    return output.getvalue()


def _sync_to_gemini(app_name: str, language: str, filename: str, file_bytes: bytes) -> bool:
    store_name = _get_store_name(app_name, language)
    if not store_name:
        return False

    mgr = _get_or_create_manager()
    try:
        existing = mgr.list_files(store_name)
        for doc in existing:
            if doc.display_name == filename:
                mgr.delete_file(doc.name)
                break
    except Exception:
        pass

    suffix = Path(filename).suffix or ".tmp"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        mgr.upload_file(store_name, tmp_path, filename)
        return True
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _delete_from_gemini(app_name: str, language: str, filename: str) -> bool:
    store_name = _get_store_name(app_name, language)
    if not store_name:
        return False

    mgr = _get_or_create_manager()
    existing = mgr.list_files(store_name)
    for doc in existing:
        if doc.display_name == filename:
            mgr.delete_file(doc.name)
            return True
    return False


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
        content = _extract_docx_text_from_bytes(file_bytes)
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
            new_bytes = _write_docx_text_to_bytes(old_bytes, req.content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {e}")
    else:
        new_bytes = req.content.encode("utf-8")

    updated = store.update_file_content(language, safe_name, new_bytes, namespace=namespace)
    if not updated:
        raise HTTPException(status_code=404, detail="檔案不存在")

    if _get_store_name(namespace, language):
        try:
            _sync_to_gemini(namespace, language, safe_name, new_bytes)
        except Exception as e:
            return {"message": f"已更新，但 Gemini 同步失敗: {e}", "synced": False, "app": namespace}

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

    gemini_synced = False
    if _get_store_name(namespace, language):
        try:
            gemini_synced = _sync_to_gemini(namespace, language, saved["name"], file_bytes)
        except Exception as e:
            print(f"[CMS KB] Gemini sync failed for {namespace}/{saved['name']}: {e}")

    return {
        "name": saved["name"],
        "display_name": saved["display_name"],
        "size": saved["size"],
        "synced": gemini_synced,
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
    store.delete_file(language, safe_name, namespace=namespace)

    if _get_store_name(namespace, language):
        try:
            _delete_from_gemini(namespace, language, safe_name)
        except Exception as e:
            print(f"[CMS KB] Gemini delete failed for {namespace}/{safe_name}: {e}")

    return {"message": "已刪除", "app": namespace}
