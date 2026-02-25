"""
JTI 知識庫管理 API

MongoDB + Gemini File Search Store 同步管理。
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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import verify_auth
from app.deps import _get_or_create_manager
from app.services.knowledge_store import get_knowledge_store

router = APIRouter(prefix="/api/jti/knowledge", tags=["JTI Knowledge Base"])

EDITABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".docx"}
TEXT_PREVIEW_EXTENSIONS = EDITABLE_EXTENSIONS | {".log", ".py", ".js", ".html"}


def _get_store_name(language: str) -> str | None:
    """取得對應語言的 File Search Store 資源名稱（可選）"""
    env_key = f"GEMINI_FILE_SEARCH_STORE_ID_{language.upper()}"
    store_id = os.getenv(env_key) or os.getenv("GEMINI_FILE_SEARCH_STORE_ID")
    if not store_id:
        return None
    return f"fileSearchStores/{store_id}"


def _safe_filename(name: str) -> str:
    """防止路徑遍歷"""
    return Path(name).name


def _extract_docx_text_from_bytes(data: bytes) -> str:
    """從 .docx bytes 提取純文字（使用 stdlib）"""
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
    """將純文字寫回 .docx bytes（替換 word/document.xml 中的段落）"""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    with zipfile.ZipFile(io.BytesIO(original_data), "r") as zf:
        xml_content = zf.read("word/document.xml")

    root = ET.fromstring(xml_content)
    body = root.find(f"{{{ns}}}body")
    if body is None:
        raise ValueError("docx 格式異常：找不到 body")

    # 移除舊段落，保留非段落元素（如 sectPr）
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


def _sync_to_gemini(language: str, filename: str, file_bytes: bytes) -> bool:
    """同步檔案內容到 Gemini File Search（透過 tempfile）"""
    store_name = _get_store_name(language)
    if not store_name:
        return False

    mgr = _get_or_create_manager()

    # 先刪除舊的同名檔案
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


def _delete_from_gemini(language: str, filename: str) -> bool:
    """刪除 Gemini File Search 中同名檔案"""
    store_name = _get_store_name(language)
    if not store_name:
        return False

    mgr = _get_or_create_manager()
    existing = mgr.list_files(store_name)
    for doc in existing:
        if doc.display_name == filename:
            mgr.delete_file(doc.name)
            return True
    return False


# ========== 列出檔案 ==========


@router.get("/files/")
def list_knowledge_files(language: str = "zh", auth: dict = Depends(verify_auth)):
    """列出知識庫中的檔案"""
    store = get_knowledge_store()
    files = store.list_files(language)
    return {"files": files, "language": language}


# ========== 讀取檔案內容 ==========


@router.get("/files/{filename}/content")
def get_file_content(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """讀取檔案內容（僅支援文字檔）"""
    safe_name = _safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(language, safe_name)
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
    safe_name = _safe_filename(filename)
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
    safe_name = _safe_filename(filename)
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
            new_bytes = _write_docx_text_to_bytes(old_bytes, req.content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {e}")
    else:
        new_bytes = req.content.encode("utf-8")

    updated = store.update_file_content(language, safe_name, new_bytes)
    if not updated:
        raise HTTPException(status_code=404, detail="檔案不存在")

    if _get_store_name(language):
        try:
            _sync_to_gemini(language, safe_name, new_bytes)
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
    )

    gemini_synced = False
    if _get_store_name(language):
        try:
            gemini_synced = _sync_to_gemini(language, saved["name"], file_bytes)
        except Exception as e:
            print(f"[KB] Gemini sync failed for {saved['name']}: {e}")

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
    safe_name = _safe_filename(filename)
    store = get_knowledge_store()
    store.delete_file(language, safe_name)

    if _get_store_name(language):
        try:
            _delete_from_gemini(language, safe_name)
        except Exception as e:
            print(f"[KB] Gemini delete failed for {safe_name}: {e}")

    return {"message": "已刪除"}
