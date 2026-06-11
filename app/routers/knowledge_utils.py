"""
Shared utilities for knowledge management routers (JTI and HCIoT).

Contains common file operations, docx processing, and RAG sync logic.
"""

from collections import defaultdict
import io
import logging
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Protocol

from fastapi import HTTPException, Request

from app.services.rag.backfill import get_backfill_service

logger = logging.getLogger(__name__)

EDITABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".docx"}
TEXT_PREVIEW_EXTENSIONS = EDITABLE_EXTENSIONS | {".log", ".py", ".js", ".html"}
ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".txt", ".md", ".docx", ".xlsx"}
MAX_SINGLE_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_UPLOAD_FILES = 1000
MAX_TOTAL_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
UPLOAD_RATE_LIMIT = 10
UPLOAD_RATE_WINDOW_SECONDS = 60


class KnowledgeStoreProtocol(Protocol):
    """Minimal interface shared by JTI and HCIoT knowledge stores."""

    def list_files(self, language: str) -> list[dict[str, Any]]: ...
    def delete_file(self, language: str, filename: str) -> bool: ...
    def insert_file(self, language: str, filename: str, data: bytes, **kwargs: Any) -> dict[str, Any]: ...


def safe_filename(name: str) -> str:
    """Sanitize filename to prevent path traversal."""
    return Path(name).name


def extract_docx_text(data: bytes) -> str:
    """Extract plain text from .docx bytes using stdlib XML parsing."""
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


def write_docx_text(original_data: bytes, text: str) -> bytes:
    """Replace paragraph text in a .docx file, preserving other XML elements."""
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


def sync_to_rag(source_type: str, language: str, filename: str, file_bytes: bytes) -> None:
    """Index a file into the local RAG store."""
    get_backfill_service().index_single_file(source_type, language, filename, file_bytes)


def delete_from_rag(source_type: str, language: str, filename: str) -> None:
    """Remove a file from the local RAG store."""
    get_backfill_service().delete_from_rag(source_type, filename, language=language)


def xlsx_to_csv_bytes(xlsx_bytes: bytes) -> bytes:
    """Convert all sheets of an xlsx file into a single CSV (sheets separated by a blank row)."""
    import csv
    import io
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    try:
        for worksheet in workbook.worksheets:
            for row in worksheet.iter_rows(values_only=True):
                writer.writerow(["" if value is None else value for value in row])
            writer.writerow([])  # blank row between sheets
    finally:
        workbook.close()

    return buffer.getvalue().encode("utf-8")


class SimpleRateLimiter:
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        self.requests[key] = [t for t in self.requests[key] if now - t < self.window_seconds]
        if len(self.requests[key]) >= self.requests_limit:
            return False
        self.requests[key].append(now)
        return True


upload_rate_limiter = SimpleRateLimiter(
    requests_limit=UPLOAD_RATE_LIMIT,
    window_seconds=UPLOAD_RATE_WINDOW_SECONDS,
)


def check_upload_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not upload_rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="上傳頻率過高，請稍後再試")


def _stored_file_matches_name(file_info: dict, filename: str) -> bool:
    return file_info.get("filename") == filename or file_info.get("name") == filename


def validate_upload_limits(files: list[dict], new_file_name: str, new_file_bytes: bytes) -> None:
    ext = Path(new_file_name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支援的檔案格式，僅支援 .docx, .txt, .md, .csv, .xlsx")

    new_size = len(new_file_bytes)
    if new_size > MAX_SINGLE_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="單一檔案大小不可超過 5 MB")

    existing_file = next((item for item in files if _stored_file_matches_name(item, new_file_name)), None)
    if existing_file is None and len(files) >= MAX_TOTAL_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail="知識庫檔案數量已達上限 (500 個檔案)")

    existing_size = sum(f.get("size", 0) for f in files)
    replaced_size = existing_file.get("size", 0) if existing_file else 0
    total_size = existing_size - replaced_size + new_size
    if total_size > MAX_TOTAL_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="知識庫總容量已達上限 (50 MB)")
