"""
Shared utilities for knowledge management routers (JTI and HCIoT).

Contains common file operations, docx processing, and Gemini sync logic.
"""

import io
import logging
import os
import tempfile
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from app.deps import _get_or_create_manager

# Recently uploaded files may not yet appear in Gemini; skip deletion during sync.
_GEMINI_SYNC_GRACE_SECONDS = 120

logger = logging.getLogger(__name__)

EDITABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".docx"}
TEXT_PREVIEW_EXTENSIONS = EDITABLE_EXTENSIONS | {".log", ".py", ".js", ".html"}


class KnowledgeStoreProtocol(Protocol):
    """Minimal interface shared by JTI and HCIoT knowledge stores."""

    def list_files(self, language: str, **kwargs: Any) -> list[dict[str, Any]]: ...
    def delete_file(self, language: str, filename: str, **kwargs: Any) -> bool: ...
    def insert_file(self, language: str, filename: str, data: bytes, **kwargs: Any) -> dict[str, Any]: ...


def safe_filename(name: str) -> str:
    """Sanitize filename to prevent path traversal."""
    return Path(name).name


def get_store_name(env_prefix: str, language: str, fallback_env_key: str | None = None) -> str | None:
    """Build the Gemini File Search Store resource name from env vars.

    Tries {PREFIX}_STORE_ID_{LANGUAGE} first, then falls back to
    *fallback_env_key* (if given) or {PREFIX}_STORE_ID.
    """
    fallback = fallback_env_key or f"{env_prefix}_STORE_ID"
    store_id = os.getenv(f"{env_prefix}_STORE_ID_{language.upper()}") or os.getenv(fallback)
    if not store_id:
        return None
    if store_id.startswith("fileSearchStores/"):
        return store_id
    return f"fileSearchStores/{store_id}"


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


def sync_to_gemini(store_name: str, filename: str, file_bytes: bytes) -> bool:
    """Upload a file to Gemini File Search, replacing all existing files with the same name."""
    mgr = _get_or_create_manager()
    delete_from_gemini(store_name, filename)

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


def delete_from_gemini(store_name: str, filename: str) -> int:
    """Delete all files from Gemini File Search that share the same display name."""
    mgr = _get_or_create_manager()
    existing = mgr.list_files(store_name)
    deleted_count = 0
    for doc in existing:
        if doc.display_name == filename:
            mgr.delete_file(doc.name)
            deleted_count += 1
    return deleted_count


def sync_gemini_db_background(
    store_name: str,
    store: KnowledgeStoreProtocol,
    language: str,
    log_prefix: str,
    insert_kwargs: dict[str, Any] | None = None,
) -> None:
    """Background sync: remove DB-only entries, register Gemini-only entries.

    Args:
        store_name: Gemini File Search Store resource name.
        store: Knowledge store instance for DB operations.
        language: Language partition key.
        log_prefix: Label for log messages (e.g. "JTI sync", "HCIoT sync").
        insert_kwargs: Extra keyword arguments passed to store.insert_file for new entries.
    """
    extra_kwargs = insert_kwargs or {}
    try:
        mgr = _get_or_create_manager()

        gemini_docs = _list_files_with_retry(mgr, store_name, log_prefix)
        if gemini_docs is None:
            return

        gemini_names = {d.display_name for d in gemini_docs}
        db_files = store.list_files(language)
        db_names = {f["display_name"] for f in db_files}

        now = datetime.now(timezone.utc)
        for f in db_files:
            if f["display_name"] not in gemini_names:
                # Skip recently created files — Gemini sync may still be in progress
                created = f.get("created_at")
                if isinstance(created, datetime):
                    age = (now - created).total_seconds()
                    if age < _GEMINI_SYNC_GRACE_SECONDS:
                        logger.info(f"[{log_prefix}] DB-only but recent ({age:.0f}s), skipping: {f['display_name']}")
                        continue
                logger.info(f"[{log_prefix}] DB-only, removing: {f['display_name']}")
                store.delete_file(language, f["name"])

        for doc in gemini_docs:
            if doc.display_name not in db_names:
                logger.info(f"[{log_prefix}] Gemini-only, registering: {doc.display_name}")
                store.insert_file(language, doc.display_name, b"", editable=False, **extra_kwargs)
                db_names.add(doc.display_name)
    except Exception as e:
        logger.warning(f"[{log_prefix}] background sync error: {e}")


def start_background_sync(
    env_prefix: str,
    get_store: Callable[[], KnowledgeStoreProtocol],
    language: str,
    log_prefix: str,
    insert_kwargs: dict[str, Any] | None = None,
    fallback_env_key: str | None = None,
) -> None:
    """Fire-and-forget background Gemini/DB sync in a daemon thread.

    Args:
        env_prefix: Environment variable prefix (e.g. "JTI", "HCIOT").
        get_store: Factory function that returns the knowledge store instance.
        language: Language partition key.
        log_prefix: Label for log messages.
        insert_kwargs: Extra keyword arguments for store.insert_file.
        fallback_env_key: Override fallback env var for store name resolution.
    """
    store_name = get_store_name(env_prefix, language, fallback_env_key=fallback_env_key)
    if not store_name:
        return

    def _run() -> None:
        store = get_store()
        sync_gemini_db_background(store_name, store, language, log_prefix, insert_kwargs)

    threading.Thread(target=_run, daemon=True).start()


def _list_files_with_retry(mgr: Any, store_name: str, log_prefix: str, max_attempts: int = 3) -> list[Any] | None:
    """List files from Gemini with retry on 503 errors."""
    for attempt in range(max_attempts):
        try:
            return mgr.list_files(store_name)
        except Exception as e:
            if "503" in str(e) and attempt < max_attempts - 1:
                time.sleep(1)
                continue
            logger.warning(f"[{log_prefix}] Gemini list failed: {e}")
            return None
    return None
