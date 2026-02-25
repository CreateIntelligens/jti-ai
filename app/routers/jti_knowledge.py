"""
JTI 知識庫管理 API

本地檔案 + Gemini File Search Store 同步管理。
檔案儲存在 data/knowledge/{language}/ 目錄下。
"""

import os
import shutil
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import verify_auth
from app.deps import _get_or_create_manager

router = APIRouter(prefix="/api/jti/knowledge", tags=["JTI Knowledge Base"])

# 本地知識庫根目錄（Docker 中為 /app/data/knowledge）
KB_ROOT = Path(os.getenv("KB_ROOT", "data/knowledge"))


def _get_kb_dir(language: str) -> Path:
    """取得語言對應的本地知識庫目錄"""
    kb_dir = KB_ROOT / language
    kb_dir.mkdir(parents=True, exist_ok=True)
    return kb_dir


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


def _extract_docx_text(file_path: Path) -> str:
    """從 .docx 提取純文字（使用 stdlib，不需額外套件）"""
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            xml_content = z.read('word/document.xml')
        root = ET.fromstring(xml_content)
        paragraphs = []
        for p in root.iter(f'{ns}p'):
            texts = [t.text or '' for t in p.iter(f'{ns}t')]
            paragraphs.append(''.join(texts))
        return '\n'.join(paragraphs)
    except Exception as e:
        return f'[無法解析 docx: {e}]'


def _write_docx_text(file_path: Path, text: str) -> None:
    """將純文字寫回 .docx（替換 word/document.xml 中的段落）"""
    import tempfile
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

    with zipfile.ZipFile(file_path, 'r') as z_in:
        original_xml = z_in.read('word/document.xml')
        root = ET.fromstring(original_xml)

    # 找到 body
    body = root.find(f'{{{ns}}}body')
    if body is None:
        raise ValueError('docx 格式異常：找不到 body')

    # 移除舊的段落，保留非段落元素（如 sectPr）
    non_para = []
    for child in list(body):
        if child.tag == f'{{{ns}}}p':
            body.remove(child)
        else:
            non_para.append(child)
            body.remove(child)

    # 建立新段落
    for line in text.split('\n'):
        p = ET.SubElement(body, f'{{{ns}}}p')
        r = ET.SubElement(p, f'{{{ns}}}r')
        t = ET.SubElement(r, f'{{{ns}}}t')
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        t.text = line

    # 加回非段落元素
    for elem in non_para:
        body.append(elem)

    # 寫回 zip
    new_xml = ET.tostring(root, encoding='unicode', xml_declaration=True)
    fd, tmp_path = tempfile.mkstemp(suffix='.docx')
    os.close(fd)
    try:
        with zipfile.ZipFile(file_path, 'r') as z_in:
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
                for item in z_in.infolist():
                    if item.filename == 'word/document.xml':
                        z_out.writestr(item, new_xml)
                    else:
                        z_out.writestr(item, z_in.read(item.filename))
        # 用暫存檔覆蓋原檔
        shutil.move(tmp_path, str(file_path))
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


# ========== 列出檔案 ==========

@router.get("/files/")
def list_knowledge_files(language: str = "zh", auth: dict = Depends(verify_auth)):
    """列出本地知識庫中的檔案"""
    kb_dir = _get_kb_dir(language)
    files = []
    for f in sorted(kb_dir.iterdir()):
        if f.is_file() and not f.name.startswith('.'):
            files.append({
                "name": f.name,
                "display_name": f.name,
                "size": f.stat().st_size,
                "editable": f.suffix.lower() in {'.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.docx'},
            })
    return {"files": files, "language": language}


# ========== 讀取檔案內容 ==========

@router.get("/files/{filename}/content")
def get_file_content(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """讀取檔案內容（僅支援文字檔）"""
    safe_name = _safe_filename(filename)
    file_path = _get_kb_dir(language) / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="檔案不存在")

    # 判斷是否為文字檔
    ext = file_path.suffix.lower()
    text_exts = {'.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.log', '.py', '.js', '.html'}

    # docx 特殊處理：可預覽且可編輯
    if ext == '.docx':
        content = _extract_docx_text(file_path)
        return {
            "filename": safe_name,
            "editable": True,
            "content": content,
            "size": file_path.stat().st_size,
        }

    if ext not in text_exts:
        return {
            "filename": safe_name,
            "editable": False,
            "content": None,
            "message": "此檔案格式不支援線上預覽，請下載查看",
        }

    try:
        content = file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = file_path.read_text(encoding='utf-8', errors='replace')

    return {
        "filename": safe_name,
        "editable": True,
        "content": content,
        "size": file_path.stat().st_size,
    }


# ========== 下載檔案 ==========

@router.get("/files/{filename}/download")
def download_file(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """下載知識庫檔案"""
    safe_name = _safe_filename(filename)
    file_path = _get_kb_dir(language) / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="檔案不存在")
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="application/octet-stream",
    )


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
    file_path = _get_kb_dir(language) / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="檔案不存在")

    ext = file_path.suffix.lower()
    editable_exts = {'.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.docx'}
    if ext not in editable_exts:
        raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

    # docx 特殊處理
    if ext == '.docx':
        try:
            _write_docx_text(file_path, req.content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {e}")
    else:
        file_path.write_text(req.content, encoding='utf-8')

    # 同步到 Gemini File Search（如果有設定 Store）
    store_name = _get_store_name(language)
    if store_name:
        try:
            mgr = _get_or_create_manager()
            # 先刪除舊的同名檔案
            try:
                existing = mgr.list_files(store_name)
                for doc in existing:
                    if doc.display_name == safe_name:
                        mgr.delete_file(doc.name)
                        break
            except Exception:
                pass
            # 重新上傳
            mgr.upload_file(store_name, str(file_path), safe_name)
        except Exception as e:
            # 本地已更新成功，Gemini 同步失敗不阻塞
            return {"message": f"本地已更新，但 Gemini 同步失敗: {e}", "synced": False}

    return {"message": "已更新", "synced": True}


# ========== 上傳檔案 ==========

@router.post("/upload/")
async def upload_knowledge_file(
    language: str = "zh",
    file: UploadFile = File(...),
    auth: dict = Depends(verify_auth),
):
    """上傳檔案到本地知識庫 + Gemini File Search"""
    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = _safe_filename(display_name)
    kb_dir = _get_kb_dir(language)
    file_path = kb_dir / safe_name

    # 如果同名檔案已存在，加上編號
    if file_path.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        counter = 1
        while file_path.exists():
            file_path = kb_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        safe_name = file_path.name

    # 儲存到本地
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 同步到 Gemini File Search
    store_name = _get_store_name(language)
    gemini_synced = False
    if store_name:
        try:
            mgr = _get_or_create_manager()
            mgr.upload_file(store_name, str(file_path), safe_name)
            gemini_synced = True
        except Exception as e:
            print(f"[KB] Gemini sync failed for {safe_name}: {e}")

    return {
        "name": safe_name,
        "display_name": safe_name,
        "size": file_path.stat().st_size,
        "synced": gemini_synced,
    }


# ========== 刪除檔案 ==========

@router.delete("/files/{filename}")
def delete_knowledge_file(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """刪除本地檔案 + Gemini File Search 中的對應文件"""
    safe_name = _safe_filename(filename)
    file_path = _get_kb_dir(language) / safe_name

    # 刪除本地
    if file_path.exists():
        file_path.unlink()

    # 刪除 Gemini 中的文件
    store_name = _get_store_name(language)
    if store_name:
        try:
            mgr = _get_or_create_manager()
            existing = mgr.list_files(store_name)
            for doc in existing:
                if doc.display_name == safe_name:
                    mgr.delete_file(doc.name)
                    break
        except Exception as e:
            print(f"[KB] Gemini delete failed for {safe_name}: {e}")

    return {"message": "已刪除"}
