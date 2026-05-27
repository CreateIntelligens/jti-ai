"""
HCIoT knowledge management API.
"""

import csv
import io
import json
import logging
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.auth import verify_admin
from app.routers.knowledge_utils import (
    EDITABLE_EXTENSIONS,
    TEXT_PREVIEW_EXTENSIONS,
    delete_from_rag,
    extract_docx_text,
    safe_filename,
    sync_to_rag,
    write_docx_text,
    xlsx_to_csv_bytes,
)
from app.services.hciot.csv_utils import (
    UnsupportedQaCsvError,
    _parse_csv_rows,
    extract_questions_from_csv,
    merge_csv_files,
    normalize_qa_csv_rows,
    split_qa_csv_by_image,
    validate_supported_hciot_csv,
)
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.hciot.main_agent import invalidate_hciot_file_map
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


def _build_merged_topic_id(category_id: str | None, topic_id: str | None) -> str | None:
    if topic_id and "/" in topic_id:
        return topic_id.strip()
    if category_id and topic_id:
        return f"{category_id.strip()}/{topic_id.strip()}"
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


def _prepare_csv_bytes(file_bytes: bytes) -> bytes:
    try:
        validate_supported_hciot_csv(file_bytes)
    except UnsupportedQaCsvError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return normalize_qa_csv_rows(file_bytes) or file_bytes


def _existing_topic_questions(language: str, topic_id: str | None) -> set[str]:
    if not topic_id:
        return set()
    store = get_hciot_knowledge_store()
    docs = store.get_topic_csv_files(language, topic_id)
    seen: set[str] = set()
    for doc in docs:
        seen.update(
            question.strip()
            for question in extract_questions_from_csv(doc.get("data") or b"") or []
            if question.strip()
        )
    return seen


def _skipped_duplicate_upload_response(
    *,
    filename: str,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
) -> dict:
    return {
        "name": "",
        "display_name": filename,
        "size": 0,
        "synced": False,
        "topic_synced": False,
        "topic_id": topic_id,
        "category_label": category_label,
        "topic_label": topic_label,
        "uploaded_count": 0,
        "uploaded_files": [],
        "imported_count": 0,
        "skipped_all_duplicates": True,
    }


def _uploaded_csv_response(
    *,
    saved_files: list[dict],
    topic_synced: bool,
    imported_count: int,
) -> dict:
    primary = saved_files[0]
    return {
        "name": primary["name"],
        "display_name": primary["display_name"],
        "size": primary["size"],
        "synced": False,
        "topic_synced": topic_synced,
        "topic_id": primary.get("topic_id"),
        "category_label": primary.get("category_label"),
        "topic_label": primary.get("topic_label"),
        "uploaded_count": len(saved_files),
        "uploaded_files": [item["name"] for item in saved_files],
        "imported_count": imported_count,
    }


def _filter_csv_rows_by_existing_questions(file_bytes: bytes, existing: set[str]) -> bytes | None:
    """Drop rows whose question already exists. Returns None if every row is a duplicate."""
    if not existing:
        return file_bytes
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return file_bytes
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "q" not in reader.fieldnames:
        return file_bytes
    kept_rows: list[dict[str, str]] = []
    for row in reader:
        q = (row.get("q") or "").strip()
        if not q or q in existing:
            continue
        kept_rows.append(row)
    if not kept_rows:
        return None
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(reader.fieldnames), lineterminator="\n")
    writer.writeheader()
    for row in kept_rows:
        writer.writerow(row)
    return out.getvalue().encode("utf-8")


def save_qa_csv_to_topic(
    *,
    background_tasks: BackgroundTasks,
    language: str,
    csv_bytes: bytes,
    filename: str,
    content_type: str,
    editable: bool,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
    hidden_questions: list[str] | None,
) -> dict:
    """Shared write path for any QA-CSV ingestion (file upload, paste, AI extraction).

    Handles dedup against existing topic questions, splits image-bearing rows, writes
    to the store + schedules RAG sync, and syncs the topic question list. Returns a
    response dict matching the /upload/ shape (or a `skipped_all_duplicates` payload).
    """
    if topic_id:
        existing = _existing_topic_questions(language, topic_id)
        filtered = _filter_csv_rows_by_existing_questions(csv_bytes, existing)
        if filtered is None:
            return _skipped_duplicate_upload_response(
                filename=filename,
                topic_id=topic_id,
                category_label=category_label,
                topic_label=topic_label,
            )
        csv_bytes = filtered

    imported_count = len(extract_questions_from_csv(csv_bytes) or [])

    uploads = split_qa_csv_by_image(csv_bytes, filename) or [(filename, csv_bytes)]

    saved_files = []
    for upload_name, upload_bytes in uploads:
        saved = _insert_uploaded_file(
            language=language,
            filename=upload_name,
            file_bytes=upload_bytes,
            content_type=content_type,
            editable=editable,
            topic_id=topic_id,
            category_label=category_label,
            topic_label=topic_label,
        )
        saved_files.append(saved)
        _schedule_rag_sync(background_tasks, language, saved["name"], upload_bytes)

    topic_synced = _sync_topic_questions_from_store(
        language=language,
        topic_id=topic_id,
        topic_label=topic_label,
        category_label=category_label,
        hidden_questions=hidden_questions,
    )

    invalidate_hciot_file_map(language)
    return _uploaded_csv_response(
        saved_files=saved_files,
        topic_synced=topic_synced,
        imported_count=imported_count,
    )


def _fallback_upload_error_response(detail: object) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": detail,
            "error_code": "unrecognized_format",
            "can_fallback_to_ai": True,
        },
    )


def _insert_uploaded_file(
    *,
    language: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    editable: bool,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
):
    return get_hciot_knowledge_store().insert_file(
        language=language,
        filename=filename,
        data=file_bytes,
        display_name=filename,
        content_type=content_type,
        editable=editable,
        topic_id=topic_id,
        category_label=category_label,
        topic_label=topic_label,
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
        topic_label=doc.get("topic_label"),
        category_label=doc.get("category_label"),
    )


def _sync_topic_questions_from_store(
    *,
    language: str,
    topic_id: str | None,
    topic_label: str | None,
    category_label: str | None,
    hidden_questions: list[str] | None = None,
) -> bool:
    """Merge question lists from all topic CSV files and sync topic store.

    When ``hidden_questions`` is provided (e.g. the admin picked which questions
    to hide at upload time), its intersection with the freshly extracted
    questions is written to ``hidden_questions.{language}`` in the *same*
    ``update_topic`` call as ``questions`` — an atomic write with no transient
    "all visible" state. When ``None`` (CSV edits, deletes, metadata moves), the
    existing ``hidden_questions`` is preserved and only stale entries pruned.
    """
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

    topic_store = get_hciot_topic_store(language)
    prefix, suffix = topic_id.split("/", 1)
    current_questions = set(questions)

    def _resolve_hidden(existing_topic: dict | None) -> list[str]:
        """Intersect the desired hidden list with questions that actually exist."""
        if hidden_questions is not None:
            return [q for q in hidden_questions if q in current_questions]
        existing_hidden = _get_topic_hidden_questions(existing_topic, language)
        return [q for q in existing_hidden if q in current_questions]

    existing = topic_store.get_topic(topic_id)
    if existing:
        if not questions and not store.has_non_csv_files(language, topic_id):
            topic_store.delete_topic(topic_id)
            logger.info("[HCIoT KB] Deleted empty topic %s", topic_id)
        else:
            topic_store.update_topic(topic_id, {
                f"questions.{language}": questions,
                f"hidden_questions.{language}": _resolve_hidden(existing),
            })
            logger.info("[HCIoT KB] Synced %d questions -> %s", len(questions), topic_id)
        return True

    if not questions:
        return False

    other_lang = get_other_language(language)
    # Label fallback: explicit user input wins, otherwise reuse the slug part of
    # the topic_id ("prefix/suffix") so the topic still has a readable display name.
    topic_label_resolved = (topic_label or "").strip() or suffix
    category_label_resolved = (category_label or "").strip() or prefix
    topic_store.upsert_topic(
        topic_id,
        {
            "labels": {
                language: topic_label_resolved,
                other_lang: "",
            },
            "category_labels": {
                language: category_label_resolved,
                other_lang: "",
            },
            "questions": {language: questions, other_lang: []},
            "hidden_questions": {language: _resolve_hidden(None), other_lang: []},
        },
    )
    logger.info("[HCIoT KB] Synced %d questions -> %s", len(questions), topic_id)
    return True


@router.get("/files/")
def list_knowledge_files(language: str = "zh"):
    store = get_hciot_knowledge_store()
    files = store.list_files(language)
    return {"files": files, "language": language}


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
    category_label: str | None = None
    topic_label: str | None = None


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
            category_label=doc.get("category_label"),
            topic_label=doc.get("topic_label"),
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

    is_document = not doc.get("topic_id")
    is_topic_csv = ext == ".csv" and not is_document

    if is_topic_csv:
        new_bytes = _prepare_csv_bytes(new_bytes)

    if is_topic_csv:
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

        if not is_document:
            _schedule_rag_sync(background_tasks, language, safe_name, new_bytes)

    topic_synced = _sync_topic_questions_for_doc(language, doc) if not is_document else False

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


def _get_topic_hidden_questions(topic: dict | None, language: str) -> list[str]:
    """Retrieve the list of hidden questions for a specific language from a topic dictionary."""
    if not topic:
        return []
    hidden_by_language = topic.get("hidden_questions")
    if not isinstance(hidden_by_language, dict):
        return []
    lang_hidden = hidden_by_language.get(language)
    if not isinstance(lang_hidden, list):
        return []
    return [item for item in lang_hidden if isinstance(item, str)]



def _parse_hidden_questions(raw: str | None) -> list[str] | None:
    """Parse the optional ``hidden_questions`` Form field (a JSON string array).

    Returns ``None`` when absent — preserving the existing sync behaviour — and
    a list of stripped question texts when present (so it matches the values
    produced by ``extract_questions_from_csv``).
    """
    if raw is None:
        return None

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(status_code=400, detail="hidden_questions 必須是 JSON 字串陣列") from e

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="hidden_questions 必須是 JSON 字串陣列")

    hidden: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if stripped:
            hidden.append(stripped)
    return hidden


@router.post("/upload/")
async def upload_knowledge_file(
    background_tasks: BackgroundTasks,
    language: str = "zh",
    file: UploadFile = File(...),
    category_id: str | None = Form(None),
    topic_id: str | None = Form(None),
    category_label: str | None = Form(None),
    topic_label: str | None = Form(None),
    skip_topic: bool = Form(False),  # noqa: ARG001 — kept for backward-compat with older clients; ignored
    hidden_questions: str | None = Form(None),
):
    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = safe_filename(display_name)
    file_bytes = await file.read()

    ext = Path(safe_name).suffix.lower()
    if ext == ".xlsx":
        try:
            file_bytes = xlsx_to_csv_bytes(file_bytes)
        except Exception as error:
            return _fallback_upload_error_response(f"XLSX 轉檔失敗: {error}")
        safe_name = Path(safe_name).with_suffix(".csv").name
        ext = ".csv"
    editable = ext in EDITABLE_EXTENSIONS
    content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    if ext == ".csv":
        try:
            parsed = _parse_csv_rows(file_bytes)
            if not parsed:
                raise HTTPException(status_code=400, detail="CSV 解析失敗")
            fieldnames, _ = parsed
            if "q" not in fieldnames or "a" not in fieldnames:
                raise HTTPException(status_code=400, detail="CSV 格式無法識別 q/a 欄位")
            file_bytes = _prepare_csv_bytes(file_bytes)
        except HTTPException as error:
            return _fallback_upload_error_response(getattr(error, "detail", str(error)))

    merged_topic_id = _build_merged_topic_id(category_id, topic_id)
    parsed_hidden = _parse_hidden_questions(hidden_questions)

    if ext == ".csv":
        return save_qa_csv_to_topic(
            background_tasks=background_tasks,
            language=language,
            csv_bytes=file_bytes,
            filename=safe_name,
            content_type=content_type,
            editable=editable,
            topic_id=merged_topic_id,
            category_label=category_label,
            topic_label=topic_label,
            hidden_questions=parsed_hidden,
        )

    saved = _insert_uploaded_file(
        language=language,
        filename=safe_name,
        file_bytes=file_bytes,
        content_type=content_type,
        editable=editable,
        topic_id=merged_topic_id,
        category_label=category_label,
        topic_label=topic_label,
    )
    _schedule_rag_sync(background_tasks, language, saved["name"], file_bytes)
    invalidate_hciot_file_map(language)
    return {
        "name": saved["name"],
        "display_name": saved["display_name"],
        "size": saved["size"],
        "synced": False,
        "topic_synced": False,
        "topic_id": saved.get("topic_id"),
        "category_label": saved.get("category_label"),
        "topic_label": saved.get("topic_label"),
        "uploaded_count": 1,
        "uploaded_files": [saved["name"]],
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

    has_topic = bool(existing.get("topic_id"))
    if has_topic:
        _schedule_rag_delete(background_tasks, language, safe_name)

    topic_synced = _sync_topic_questions_for_doc(language, existing) if has_topic else False
    invalidate_hciot_file_map(language)

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
