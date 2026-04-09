"""
HCIoT knowledge management API.
"""

import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from urllib.parse import quote

from functools import partial

from app.auth import verify_admin, verify_auth
from app.routers.knowledge_utils import (
    EDITABLE_EXTENSIONS,
    TEXT_PREVIEW_EXTENSIONS,
    delete_from_gemini,
    extract_docx_text,
    gemini_background,
    get_store_name,
    safe_filename,
    start_background_sync,
    sync_to_gemini,
    write_docx_text,
)
from app.services.hciot.csv_utils import extract_questions_from_csv, merge_csv_files, split_qa_csv_by_image
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.hciot.topic_store import get_hciot_topic_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["HCIoT Knowledge"], dependencies=[Depends(verify_admin)])

ENV_PREFIX = "HCIOT"
LOG_PREFIX = "HCIoT sync"


def _store_name(language: str) -> str | None:
    return get_store_name(ENV_PREFIX, language)


_gemini_background = partial(gemini_background, "HCIoT KB")


def _normalized_label(value: str | None, fallback: str) -> str:
    return (value or "").strip() or fallback


def _sync_topic_questions_for_doc(language: str, doc: dict | None) -> bool:
    if not doc:
        return False
    return _sync_topic_questions_from_store(
        language=language,
        topic_id=doc.get("topic_id"),
        topic_label_zh=doc.get("topic_label_zh"),
        topic_label_en=doc.get("topic_label_en"),
        category_label_zh=doc.get("category_label_zh"),
        category_label_en=doc.get("category_label_en"),
    )


def _sync_topic_questions_from_store(
    *,
    language: str,
    topic_id: str | None,
    topic_label_zh: str | None,
    topic_label_en: str | None,
    category_label_zh: str | None,
    category_label_en: str | None,
) -> bool:
    """Merge question lists from all topic CSV files and sync topic store."""
    if not topic_id or "/" not in topic_id:
        return False

    store = get_hciot_knowledge_store()
    docs = store.get_topic_csv_files(language, topic_id)

    seen: set[str] = set()
    questions: list[str] = []
    for doc in docs:
        extracted = extract_questions_from_csv(doc.get("data") or b"")
        if not extracted:
            continue
        for question in extracted:
            if question not in seen:
                seen.add(question)
                questions.append(question)

    topic_store = get_hciot_topic_store()
    prefix, suffix = topic_id.split("/", 1)

    existing = topic_store.get_topic(topic_id)
    if existing:
        topic_store.update_topic(topic_id, {"questions": {"zh": questions, "en": questions}})
        logger.info("[HCIoT KB] Synced %d questions -> %s", len(questions), topic_id)
        return True

    if not questions:
        return False

    topic_store.upsert_topic(
        topic_id,
        {
            "labels": {
                "zh": _normalized_label(topic_label_zh, suffix),
                "en": _normalized_label(topic_label_en, suffix),
            },
            "category_labels": {
                "zh": _normalized_label(category_label_zh, prefix),
                "en": _normalized_label(category_label_en, prefix),
            },
            "questions": {"zh": questions, "en": questions},
        },
    )
    logger.info("[HCIoT KB] Synced %d questions -> %s", len(questions), topic_id)
    return True


@router.get("/files/")
def list_knowledge_files(language: str = "zh", auth: dict = Depends(verify_auth)):
    store = get_hciot_knowledge_store()
    files = store.list_files(language)
    start_background_sync(ENV_PREFIX, get_hciot_knowledge_store, language, LOG_PREFIX)
    return {"files": files, "language": language}


@router.get("/files/{filename}/content")
def get_file_content(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    safe_name = safe_filename(filename)
    store = get_hciot_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    ext = Path(safe_name).suffix.lower()
    file_bytes = doc.get("data", b"")

    if ext == ".docx":
        content = extract_docx_text(file_bytes)
        return {"filename": safe_name, "editable": True, "content": content, "size": doc.get("size", len(file_bytes))}

    if ext not in TEXT_PREVIEW_EXTENSIONS:
        return {
            "filename": safe_name,
            "editable": False,
            "content": None,
            "message": "此檔案格式不支援線上預覽，請下載查看",
        }

    content = file_bytes.decode("utf-8", errors="replace")
    return {"filename": safe_name, "editable": True, "content": content, "size": doc.get("size", len(file_bytes))}


@router.get("/files/{filename}/download")
def download_file(filename: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    safe_name = safe_filename(filename)
    store = get_hciot_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")

    file_bytes = doc.get("data", b"")
    content_type = doc.get("content_type") or "application/octet-stream"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"}
    return Response(content=file_bytes, media_type=content_type, headers=headers)


class UpdateContentRequest(BaseModel):
    content: str


class UpdateFileMetadataRequest(BaseModel):
    topic_id: str | None = None
    category_label_zh: str | None = None
    category_label_en: str | None = None
    topic_label_zh: str | None = None
    topic_label_en: str | None = None


@router.put("/files/{filename}/content")
async def update_file_content(
    filename: str,
    req: UpdateContentRequest,
    background_tasks: BackgroundTasks,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    safe_name = safe_filename(filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

    store = get_hciot_knowledge_store()
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

    topic_synced = _sync_topic_questions_for_doc(language, doc)

    store_name = _store_name(language)
    if store_name:
        background_tasks.add_task(_gemini_background, sync_to_gemini, store_name, safe_name, new_bytes)

    return {"message": "已更新", "synced": False, "topic_synced": topic_synced}


@router.put("/files/{filename}/metadata")
async def update_file_metadata(
    filename: str,
    request: UpdateFileMetadataRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    safe_name = safe_filename(filename)
    store = get_hciot_knowledge_store()
    existing = store.get_file(language, safe_name)
    if not existing:
        raise HTTPException(status_code=404, detail="檔案不存在")

    updated = store.update_file_metadata(language, safe_name, request.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="檔案不存在")

    topic_synced = False
    previous_topic_id = existing.get("topic_id")
    if previous_topic_id and previous_topic_id != updated.get("topic_id"):
        topic_synced = _sync_topic_questions_for_doc(language, existing) or topic_synced

    topic_synced = _sync_topic_questions_for_doc(language, updated) or topic_synced

    return {
        **updated,
        "topic_synced": topic_synced,
    }


@router.post("/upload/")
async def upload_knowledge_file(
    background_tasks: BackgroundTasks,
    language: str = "zh",
    file: UploadFile = File(...),
    category_id: str | None = Form(None),
    topic_id: str | None = Form(None),
    category_label_zh: str | None = Form(None),
    category_label_en: str | None = Form(None),
    topic_label_zh: str | None = Form(None),
    topic_label_en: str | None = Form(None),
    auth: dict = Depends(verify_auth),
):
    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = safe_filename(display_name)
    file_bytes = await file.read()

    ext = Path(safe_name).suffix.lower()
    editable = ext in EDITABLE_EXTENSIONS
    content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    # Merge category_id + topic_id into single topic_id
    merged_topic_id = None
    if category_id and topic_id:
        merged_topic_id = f"{category_id.strip()}/{topic_id.strip()}"
    elif topic_id and "/" in topic_id:
        merged_topic_id = topic_id.strip()
    elif category_id:
        merged_topic_id = category_id.strip()

    store = get_hciot_knowledge_store()
    store_name = _store_name(language)
    category_labels = {"zh": category_label_zh, "en": category_label_en}
    topic_labels = {"zh": topic_label_zh, "en": topic_label_en}
    uploads = split_qa_csv_by_image(file_bytes, safe_name) or [(safe_name, file_bytes)]
    saved_files = []
    for upload_name, upload_bytes in uploads:
        saved = store.insert_file(
            language=language,
            filename=upload_name,
            data=upload_bytes,
            display_name=upload_name,
            content_type=content_type,
            editable=editable,
            topic_id=merged_topic_id,
            category_labels=category_labels,
            topic_labels=topic_labels,
        )
        saved_files.append(saved)

        if store_name:
            background_tasks.add_task(_gemini_background, sync_to_gemini, store_name, saved["name"], upload_bytes)

    topic_synced = _sync_topic_questions_from_store(
        language=language,
        topic_id=merged_topic_id,
        topic_label_zh=topic_label_zh,
        topic_label_en=topic_label_en,
        category_label_zh=category_label_zh,
        category_label_en=category_label_en,
    )

    primary = saved_files[0]

    return {
        "name": primary["name"],
        "display_name": primary["display_name"],
        "size": primary["size"],
        "synced": False,
        "topic_synced": topic_synced,
        "topic_id": primary.get("topic_id"),
        "category_label_zh": primary.get("category_label_zh"),
        "category_label_en": primary.get("category_label_en"),
        "topic_label_zh": primary.get("topic_label_zh"),
        "topic_label_en": primary.get("topic_label_en"),
        "uploaded_count": len(saved_files),
        "uploaded_files": [item["name"] for item in saved_files],
    }


@router.delete("/files/{filename}")
async def delete_knowledge_file(
    filename: str, background_tasks: BackgroundTasks, language: str = "zh", auth: dict = Depends(verify_auth),
):
    safe_name = safe_filename(filename)
    store = get_hciot_knowledge_store()
    existing = store.get_file(language, safe_name)
    deleted = store.delete_file(language, safe_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="檔案不存在")

    store_name = _store_name(language)
    if store_name:
        background_tasks.add_task(_gemini_background, delete_from_gemini, store_name, safe_name)

    topic_synced = _sync_topic_questions_for_doc(language, existing)

    return {
        "message": "已刪除",
        "mongo_deleted": True,
        "topic_synced": topic_synced,
    }


@router.get("/topic-csv-merged")
def get_topic_csv_merged(topic_id: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    store = get_hciot_knowledge_store()
    docs = store.get_topic_csv_files(language, topic_id)

    csv_contents = [d["data"] for d in docs if d.get("data")]
    source_files = [d["filename"] for d in docs if d.get("data")]

    rows = merge_csv_files(csv_contents, source_filenames=source_files)
    return {"rows": rows, "source_files": source_files}
