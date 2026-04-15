"""
Shared utilities for knowledge management routers (JTI and HCIoT).

Contains common file operations, docx processing, and RAG sync logic.
"""

import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Protocol

from app.services.rag.backfill import get_backfill_service

logger = logging.getLogger(__name__)

EDITABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".docx"}
TEXT_PREVIEW_EXTENSIONS = EDITABLE_EXTENSIONS | {".log", ".py", ".js", ".html"}


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
