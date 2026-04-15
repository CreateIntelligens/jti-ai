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

from app.auth import verify_admin
from app.routers.knowledge_utils import (
    EDITABLE_EXTENSIONS,
    TEXT_PREVIEW_EXTENSIONS,
    delete_from_rag,
    extract_docx_text,
    safe_filename,
    sync_to_rag,
    write_docx_text,
)
from app.services.hciot.csv_utils import extract_questions_from_csv, merge_csv_files, normalize_qa_csv_rows, split_qa_csv_by_image
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.hciot.topic_store import get_hciot_topic_store
from app.utils import get_other_language

logger = logging.getLogger(__name__)

router = APIRouter(tags=["HCIoT Knowledge"], dependencies=[Depends(verify_admin)])

SOURCE_TYPE = "hciot"


def _schedule_rag_sync(
    background_tasks: BackgroundTasks,
    language: str,
    filename: str,
    file_bytes: bytes,
) -> None:
    background_tasks.add_task(sync_to_rag, SOURCE_TYPE, language, filename, file_bytes)


def _schedule_rag_delete(
    background_tasks: BackgroundTasks,
    language: str,
    filename: str,
) -> None:
    background_tasks.add_task(delete_from_rag, SOURCE_TYPE, language, filename)


def _normalized_label(value: str | None, fallback: str) -> str:
    return (value or "").strip() or fallback




def _build_merged_topic_id(category_id: str | None, topic_id: str | None) -> str | None:
    if category_id and topic_id:
        return f"{category_id.strip()}/{topic_id.strip()}"
    if topic_id and "/" in topic_id:
        return topic_id.strip()
    if category_id:
        return category_id.strip()
    return None


def _get_doc_or_404(language: str, filename: str) -> tuple[str, dict]:
    safe_name = safe_filename(filename)
    store = get_hciot_knowledge_store()
    doc = store.get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")
    return safe_name, doc


def _insert_uploaded_file(
    *,
    language: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    editable: bool,
    topic_id: str | None,
    category_labels: dict[str, str | None],
    topic_labels: dict[str, str | None],
):
    return get_hciot_knowledge_store().insert_file(
        language=language,
        filename=filename,
        data=file_bytes,
        display_name=filename,
        content_type=content_type,
        editable=editable,
        topic_id=topic_id,
        category_labels=category_labels,
        topic_labels=topic_labels,
    )


def _last_image_filename_fragment(stem: str) -> str | None:
    upper_stem = stem.upper()
    index = upper_stem.rfind("IMG_")
    if index < 0:
        return None
    return stem[index:]


def _strip_repeated_trailing_fragment(stem: str, fragment: str) -> str:
    suffix = f"_{fragment}"
    normalized_suffix = suffix.lower()
    while stem.lower().endswith(normalized_suffix):
        stem = stem[:-len(suffix)]
    return stem


def _canonicalize_split_upload_name(current_name: str, upload_name: str) -> str:
    current_path = Path(current_name)
    upload_path = Path(upload_name)
    current_fragment = _last_image_filename_fragment(current_path.stem)
    new_fragment = _last_image_filename_fragment(upload_path.stem)
    if not current_fragment or not new_fragment:
        return upload_name

    base_stem = _strip_repeated_trailing_fragment(current_path.stem, current_fragment)
    if not base_stem:
        return upload_name

    suffix = upload_path.suffix or current_path.suffix or ".csv"
    return f"{base_stem}_{new_fragment}{suffix}"


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
        if not questions and not store.has_non_csv_files(language, topic_id):
            topic_store.delete_topic(topic_id)
            logger.info("[HCIoT KB] Deleted empty topic %s", topic_id)
        else:
            topic_store.update_topic(topic_id, {f"questions.{language}": questions})
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
            "questions": {language: questions, get_other_language(language): []},
        },
    )
    logger.info("[HCIoT KB] Synced %d questions -> %s", len(questions), topic_id)
    return True


@router.get("/files/")
def list_knowledge_files(language: str = "zh"):
    store = get_hciot_knowledge_store()
    files = store.list_files(language)
    effective_language = language
    if not files and language != "zh":
        files = store.list_files("zh")
        effective_language = "zh"
    return {"files": files, "language": effective_language}


@router.get("/files/{filename}/content")
def get_file_content(filename: str, language: str = "zh"):
    safe_name, doc = _get_doc_or_404(language, filename)

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
def download_file(filename: str, language: str = "zh"):
    safe_name, doc = _get_doc_or_404(language, filename)

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


def _rewrite_csv_file_with_split_uploads(
    *,
    store,
    language: str,
    safe_name: str,
    doc: dict,
    new_bytes: bytes,
    background_tasks: BackgroundTasks,
) -> None:
    uploads = split_qa_csv_by_image(new_bytes, safe_name)
    if uploads and "_img_" in safe_name.lower():
        uploads = [
            (_canonicalize_split_upload_name(safe_name, upload_name), upload_bytes)
            for upload_name, upload_bytes in uploads
        ]

    if not uploads:
        updated = store.update_file_content(language, safe_name, new_bytes)
        if not updated:
            raise HTTPException(status_code=404, detail="檔案不存在")

        _schedule_rag_sync(background_tasks, language, safe_name, new_bytes)
        return

    upload_map = {name: data for name, data in uploads}
    target_names = set(upload_map)

    if safe_name in target_names:
        safe_name_bytes = upload_map.pop(safe_name)
        updated = store.update_file_content(language, safe_name, safe_name_bytes)
        if not updated:
            raise HTTPException(status_code=404, detail="檔案不存在")
        _schedule_rag_sync(background_tasks, language, safe_name, safe_name_bytes)
    else:
        deleted = store.delete_file(language, safe_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="檔案不存在")
        _schedule_rag_delete(background_tasks, language, safe_name)

    for upload_name, upload_bytes in upload_map.items():
        saved = _insert_uploaded_file(
            language=language,
            filename=upload_name,
            file_bytes=upload_bytes,
            content_type=doc.get("content_type") or "application/octet-stream",
            editable=bool(doc.get("editable", False)),
            topic_id=doc.get("topic_id"),
            category_labels={
                "zh": doc.get("category_label_zh"),
                "en": doc.get("category_label_en"),
            },
            topic_labels={
                "zh": doc.get("topic_label_zh"),
                "en": doc.get("topic_label_en"),
            },
        )
        _schedule_rag_sync(background_tasks, language, saved["name"], upload_bytes)


@router.put("/files/{filename}/content")
async def update_file_content(
    filename: str,
    req: UpdateContentRequest,
    background_tasks: BackgroundTasks,
    language: str = "zh",
):
    safe_name, doc = _get_doc_or_404(language, filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

    store = get_hciot_knowledge_store()

    old_bytes = doc.get("data", b"")
    if ext == ".docx":
        try:
            new_bytes = write_docx_text(old_bytes, req.content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {e}")
    else:
        new_bytes = req.content.encode("utf-8")

    if ext == ".csv":
        new_bytes = normalize_qa_csv_rows(new_bytes) or new_bytes

    if ext == ".csv":
        _rewrite_csv_file_with_split_uploads(
            store=store,
            language=language,
            safe_name=safe_name,
            doc=doc,
            new_bytes=new_bytes,
            background_tasks=background_tasks,
        )
    else:
        updated = store.update_file_content(language, safe_name, new_bytes)
        if not updated:
            raise HTTPException(status_code=404, detail="檔案不存在")

        _schedule_rag_sync(background_tasks, language, safe_name, new_bytes)

    topic_synced = _sync_topic_questions_for_doc(language, doc)

    return {"message": "已更新", "synced": False, "topic_synced": topic_synced}


@router.put("/files/{filename}/metadata")
async def update_file_metadata(
    filename: str,
    request: UpdateFileMetadataRequest,
    language: str = "zh",
):
    safe_name, existing = _get_doc_or_404(language, filename)
    store = get_hciot_knowledge_store()

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
):
    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = safe_filename(display_name)
    file_bytes = await file.read()

    ext = Path(safe_name).suffix.lower()
    editable = ext in EDITABLE_EXTENSIONS
    content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    if ext == ".csv":
        file_bytes = normalize_qa_csv_rows(file_bytes) or file_bytes

    merged_topic_id = _build_merged_topic_id(category_id, topic_id)

    category_labels = {"zh": category_label_zh, "en": category_label_en}
    topic_labels = {"zh": topic_label_zh, "en": topic_label_en}
    uploads = split_qa_csv_by_image(file_bytes, safe_name) or [(safe_name, file_bytes)]
    saved_files = []
    for upload_name, upload_bytes in uploads:
        saved = _insert_uploaded_file(
            language=language,
            filename=upload_name,
            file_bytes=upload_bytes,
            content_type=content_type,
            editable=editable,
            topic_id=merged_topic_id,
            category_labels=category_labels,
            topic_labels=topic_labels,
        )
        saved_files.append(saved)
        _schedule_rag_sync(background_tasks, language, saved["name"], upload_bytes)

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
    filename: str, background_tasks: BackgroundTasks, language: str = "zh",
):
    safe_name, existing = _get_doc_or_404(language, filename)
    store = get_hciot_knowledge_store()
    deleted = store.delete_file(language, safe_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="檔案不存在")

    _schedule_rag_delete(background_tasks, language, safe_name)

    topic_synced = _sync_topic_questions_for_doc(language, existing)

    return {
        "message": "已刪除",
        "mongo_deleted": True,
        "topic_synced": topic_synced,
    }


@router.get("/topic-csv-merged")
def get_topic_csv_merged(topic_id: str, language: str = "zh"):
    store = get_hciot_knowledge_store()
    docs = store.get_topic_csv_files(language, topic_id)

    csv_contents = [d["data"] for d in docs if d.get("data")]
    source_files = [d["filename"] for d in docs if d.get("data")]

    rows = merge_csv_files(csv_contents, source_filenames=source_files)
    return {"rows": rows, "source_files": source_files}
