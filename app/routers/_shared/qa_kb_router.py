"""Router factory for QA knowledge-base workspaces."""

from __future__ import annotations

import csv
import io
import json
import logging
import mimetypes
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

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
from app.services._shared.qa_kb.csv_utils import (
    UnsupportedQaCsvError,
    _parse_csv_rows,
    extract_questions_from_csv,
    merge_csv_files,
    normalize_qa_csv_rows,
    split_qa_csv_by_image,
    validate_supported_hciot_csv,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTRACT_EXTENSIONS = {".docx", ".txt", ".md", ".csv", ".xlsx"}
MAX_QA_EXTRACT_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_QA_EXTRACT_TEXT_LENGTH = 30000


@dataclass(frozen=True)
class QaKbRouterConfig:
    tag: str
    auth_dep: Callable[..., Any]
    knowledge_store_factory: Callable[[], Any]
    topic_store_factory: Callable[[str | None], Any]
    rag_source_type: str
    invalidate_cache: Callable[[str | None], None]
    other_language: Callable[[str], str]
    extract_text_from_upload: Callable[[bytes, str], str] | None = None
    run_extract_job_from_text: Callable[[str, str, str], Awaitable[None]] | None = None
    create_job: Callable[..., Any] | None = None
    get_job: Callable[[str], Any] | None = None
    update_job: Callable[..., Any] | None = None
    delete_job: Callable[[str], Any] | None = None
    persona_loader: Callable[[str], tuple[str, str]] | None = None
    qa_extractor: Callable[..., Awaitable[list[dict[str, str]]]] | None = None


class UpdateContentRequest(BaseModel):
    content: str


class UpdateFileMetadataRequest(BaseModel):
    topic_id: str | None = None
    category_label: str | None = None
    topic_label: str | None = None


class QaPairImport(BaseModel):
    q: str
    a: str


class ImportQaRequest(BaseModel):
    qa_pairs: list[QaPairImport]
    hidden_questions: list[str] | None = None


def _required(value: Any, name: str) -> Any:
    if value is None:
        raise RuntimeError(f"QaKbRouterConfig.{name} is required for this route")
    return value


def _schedule_rag_sync(
    config: QaKbRouterConfig,
    background_tasks: BackgroundTasks,
    language: str,
    filename: str,
    file_bytes: bytes,
) -> None:
    background_tasks.add_task(sync_to_rag, config.rag_source_type, language, filename, file_bytes)


def _schedule_rag_delete(
    config: QaKbRouterConfig,
    background_tasks: BackgroundTasks,
    language: str,
    filename: str,
) -> None:
    background_tasks.add_task(delete_from_rag, config.rag_source_type, language, filename)


def _build_merged_topic_id(category_id: str | None, topic_id: str | None) -> str | None:
    if topic_id and "/" in topic_id:
        return topic_id.strip()
    if category_id and topic_id:
        return f"{category_id.strip()}/{topic_id.strip()}"
    if category_id:
        return category_id.strip()
    return None


def _get_doc_or_404(config: QaKbRouterConfig, language: str, filename: str) -> tuple[str, dict]:
    safe_name = safe_filename(filename)
    doc = config.knowledge_store_factory().get_file(language, safe_name)
    if not doc:
        raise HTTPException(status_code=404, detail="檔案不存在")
    return safe_name, doc


def _prepare_csv_bytes(file_bytes: bytes) -> bytes:
    try:
        validate_supported_hciot_csv(file_bytes)
    except UnsupportedQaCsvError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return normalize_qa_csv_rows(file_bytes) or file_bytes


def _existing_topic_questions(config: QaKbRouterConfig, language: str, topic_id: str | None) -> set[str]:
    if not topic_id:
        return set()
    docs = config.knowledge_store_factory().get_topic_csv_files(language, topic_id)
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


def _insert_uploaded_file(
    config: QaKbRouterConfig,
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
    return config.knowledge_store_factory().insert_file(
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


def save_qa_csv_to_topic(
    *,
    config: QaKbRouterConfig,
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
    """Shared write path for QA-CSV ingestion."""
    if topic_id:
        existing = _existing_topic_questions(config, language, topic_id)
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
            config,
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
        _schedule_rag_sync(config, background_tasks, language, saved["name"], upload_bytes)

    topic_synced = _sync_topic_questions_from_store(
        config,
        language=language,
        topic_id=topic_id,
        topic_label=topic_label,
        category_label=category_label,
        hidden_questions=hidden_questions,
    )

    config.invalidate_cache(language)
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


def _sync_topic_questions_for_doc(config: QaKbRouterConfig, language: str, doc: dict | None) -> bool:
    if not doc:
        return False
    return _sync_topic_questions_from_store(
        config,
        language=language,
        topic_id=doc.get("topic_id"),
        topic_label=doc.get("topic_label"),
        category_label=doc.get("category_label"),
    )


def _sync_topic_questions_from_store(
    config: QaKbRouterConfig,
    *,
    language: str,
    topic_id: str | None,
    topic_label: str | None,
    category_label: str | None,
    hidden_questions: list[str] | None = None,
) -> bool:
    """Merge question lists from all topic CSV files and sync topic store."""
    if not topic_id or "/" not in topic_id:
        return False

    store = config.knowledge_store_factory()
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

    topic_store = config.topic_store_factory(language)
    prefix, suffix = topic_id.split("/", 1)
    current_questions = set(questions)

    def _resolve_hidden(existing_topic: dict | None) -> list[str]:
        if hidden_questions is not None:
            return [q for q in hidden_questions if q in current_questions]
        existing_hidden = _get_topic_hidden_questions(existing_topic, language)
        return [q for q in existing_hidden if q in current_questions]

    existing = topic_store.get_topic(topic_id)
    if existing:
        if not questions and not store.has_non_csv_files(language, topic_id):
            topic_store.delete_topic(topic_id)
            logger.info("[QA KB] Deleted empty topic %s", topic_id)
        else:
            topic_store.update_topic(topic_id, {
                f"questions.{language}": questions,
                f"hidden_questions.{language}": _resolve_hidden(existing),
            })
            logger.info("[QA KB] Synced %d questions -> %s", len(questions), topic_id)
        return True

    if not questions:
        return False

    other_lang = config.other_language(language)
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
    logger.info("[QA KB] Synced %d questions -> %s", len(questions), topic_id)
    return True


def _rewrite_csv_file_with_split_uploads(
    config: QaKbRouterConfig,
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

        _schedule_rag_sync(config, background_tasks, language, safe_name, new_bytes)
        return

    upload_map = {name: data for name, data in uploads}
    target_names = set(upload_map)

    if safe_name in target_names:
        safe_name_bytes = upload_map.pop(safe_name)
        updated = store.update_file_content(language, safe_name, safe_name_bytes)
        if not updated:
            raise HTTPException(status_code=404, detail="檔案不存在")
        _schedule_rag_sync(config, background_tasks, language, safe_name, safe_name_bytes)
    else:
        deleted = store.delete_file(language, safe_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="檔案不存在")
        _schedule_rag_delete(config, background_tasks, language, safe_name)

    for upload_name, upload_bytes in upload_map.items():
        saved = _insert_uploaded_file(
            config,
            language=language,
            filename=upload_name,
            file_bytes=upload_bytes,
            content_type=doc.get("content_type") or "application/octet-stream",
            editable=bool(doc.get("editable", False)),
            topic_id=doc.get("topic_id"),
            category_label=doc.get("category_label"),
            topic_label=doc.get("topic_label"),
        )
        _schedule_rag_sync(config, background_tasks, language, saved["name"], upload_bytes)


def _get_topic_hidden_questions(topic: dict | None, language: str) -> list[str]:
    """Retrieve hidden questions for a specific language from a topic dictionary."""
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


def _extract_text_from_upload(file_bytes: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        text = extract_docx_text(file_bytes)
    elif ext in (".txt", ".md", ".csv"):
        text = file_bytes.decode("utf-8", errors="ignore")
    elif ext == ".xlsx":
        csv_bytes = xlsx_to_csv_bytes(file_bytes)
        text = csv_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"不支援的副檔名: {ext}")

    if not text.strip():
        raise ValueError("文件內容為空，無法進行問答擷取")
    return text


async def run_extract_job_from_text(
    config: QaKbRouterConfig,
    job_id: str,
    text: str,
    language: str,
) -> None:
    update_job = _required(config.update_job, "update_job")
    persona_loader = _required(config.persona_loader, "persona_loader")
    qa_extractor = _required(config.qa_extractor, "qa_extractor")
    try:
        update_job(job_id, status="running")
        persona_text, role_scope_text = persona_loader(language)
        qa_pairs = await qa_extractor(
            text=text,
            language=language,
            persona_text=persona_text,
            role_scope_text=role_scope_text,
        )
        if not qa_pairs:
            raise ValueError("未能從文件擷取任何 Q&A")
        update_job(job_id, status="done", qa_pairs=qa_pairs)
    except Exception as error:
        logger.error("[QA Extract Job] Job %s failed: %s", job_id, error)
        update_job(job_id, status="failed", error=str(error))


def _create_pending_job(
    config: QaKbRouterConfig,
    *,
    category_id: str | None,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
    language: str,
) -> str:
    create_job = _required(config.create_job, "create_job")
    job_id = str(uuid.uuid4())
    create_job(
        job_id=job_id,
        category_id=category_id,
        topic_id=topic_id,
        category_label=category_label,
        topic_label=topic_label,
        language=language,
    )
    return job_id


def _qa_pairs_to_csv_bytes(qa_pairs: list[QaPairImport]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["q", "a"], lineterminator="\n")
    writer.writeheader()
    for pair in qa_pairs:
        writer.writerow({
            "q": pair.q.strip(),
            "a": pair.a.strip(),
        })
    return output.getvalue().encode("utf-8")


def _hidden_questions_for_import(req: ImportQaRequest) -> list[str]:
    if req.hidden_questions is not None:
        return req.hidden_questions
    return [pair.q.strip() for pair in req.qa_pairs if pair.q.strip()]


def _add_knowledge_routes(router: APIRouter, config: QaKbRouterConfig) -> None:
    @router.get("/files/")
    def list_knowledge_files(language: str = "zh"):
        files = config.knowledge_store_factory().list_files(language)
        return {"files": files, "language": language}

    @router.get("/files/{filename}/content")
    def get_file_content(filename: str, language: str = "zh"):
        safe_name, doc = _get_doc_or_404(config, language, filename)

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
        safe_name, doc = _get_doc_or_404(config, language, filename)

        file_bytes = doc.get("data", b"")
        content_type = doc.get("content_type") or "application/octet-stream"
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"}
        return Response(content=file_bytes, media_type=content_type, headers=headers)

    @router.put("/files/{filename}/content")
    async def update_file_content(
        filename: str,
        req: UpdateContentRequest,
        background_tasks: BackgroundTasks,
        language: str = "zh",
    ):
        safe_name, doc = _get_doc_or_404(config, language, filename)
        ext = Path(safe_name).suffix.lower()
        if ext not in EDITABLE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

        store = config.knowledge_store_factory()

        old_bytes = doc.get("data", b"")
        if ext == ".docx":
            try:
                new_bytes = write_docx_text(old_bytes, req.content)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {e}") from e
        else:
            new_bytes = req.content.encode("utf-8")

        is_document = not doc.get("topic_id")
        is_topic_csv = ext == ".csv" and not is_document

        if is_topic_csv:
            new_bytes = _prepare_csv_bytes(new_bytes)

        if is_topic_csv:
            _rewrite_csv_file_with_split_uploads(
                config,
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
                _schedule_rag_sync(config, background_tasks, language, safe_name, new_bytes)

        topic_synced = _sync_topic_questions_for_doc(config, language, doc) if not is_document else False

        return {"message": "已更新", "synced": False, "topic_synced": topic_synced}

    @router.put("/files/{filename}/metadata")
    async def update_file_metadata(
        filename: str,
        request: UpdateFileMetadataRequest,
        language: str = "zh",
    ):
        safe_name, existing = _get_doc_or_404(config, language, filename)
        store = config.knowledge_store_factory()

        updated = store.update_file_metadata(language, safe_name, request.model_dump())
        if not updated:
            raise HTTPException(status_code=404, detail="檔案不存在")

        topic_synced = False
        previous_topic_id = existing.get("topic_id")
        if previous_topic_id and previous_topic_id != updated.get("topic_id"):
            topic_synced = _sync_topic_questions_for_doc(config, language, existing) or topic_synced

        topic_synced = _sync_topic_questions_for_doc(config, language, updated) or topic_synced

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
        category_label: str | None = Form(None),
        topic_label: str | None = Form(None),
        skip_topic: bool = Form(False),  # noqa: ARG001
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
                config=config,
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
            config,
            language=language,
            filename=safe_name,
            file_bytes=file_bytes,
            content_type=content_type,
            editable=editable,
            topic_id=merged_topic_id,
            category_label=category_label,
            topic_label=topic_label,
        )
        _schedule_rag_sync(config, background_tasks, language, saved["name"], file_bytes)
        config.invalidate_cache(language)
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
        filename: str,
        background_tasks: BackgroundTasks,
        language: str = "zh",
    ):
        safe_name, existing = _get_doc_or_404(config, language, filename)
        store = config.knowledge_store_factory()
        deleted = store.delete_file(language, safe_name)
        if not deleted:
            raise HTTPException(status_code=404, detail="檔案不存在")

        has_topic = bool(existing.get("topic_id"))
        if has_topic:
            _schedule_rag_delete(config, background_tasks, language, safe_name)

        topic_synced = _sync_topic_questions_for_doc(config, language, existing) if has_topic else False
        config.invalidate_cache(language)

        return {
            "message": "已刪除",
            "mongo_deleted": True,
            "topic_synced": topic_synced,
        }

    @router.get("/topic-csv-merged")
    def get_topic_csv_merged(topic_id: str, language: str = "zh"):
        docs = config.knowledge_store_factory().get_topic_csv_files(language, topic_id)
        csv_contents = [d["data"] for d in docs if d.get("data")]
        source_files = [d["filename"] for d in docs if d.get("data")]

        rows = merge_csv_files(csv_contents, source_filenames=source_files)
        return {"rows": rows, "source_files": source_files}


def _add_extract_routes(router: APIRouter, config: QaKbRouterConfig) -> None:
    @router.post("/qa-extract")
    async def start_qa_extraction(
        background_tasks: BackgroundTasks,
        file: UploadFile | None = File(None),
        text_input: str | None = Form(None),
        category_id: str | None = Form(None),
        topic_id: str | None = Form(None),
        category_label: str | None = Form(None),
        topic_label: str | None = Form(None),
        language: str = Form("zh"),
    ):
        if file is not None:
            display_name = file.filename or "uploaded_document"
            safe_name = safe_filename(display_name)
            ext = Path(safe_name).suffix.lower()
            if ext not in SUPPORTED_EXTRACT_EXTENSIONS:
                raise HTTPException(status_code=400, detail="不支援的檔案格式，僅支援 .docx, .txt, .md, .csv, .xlsx")

            file_bytes = await file.read()
            if len(file_bytes) > MAX_QA_EXTRACT_FILE_SIZE_BYTES:
                raise HTTPException(status_code=400, detail="檔案大小不可超過 5 MB")

            try:
                extract_text = config.extract_text_from_upload or _extract_text_from_upload
                text = extract_text(file_bytes, safe_name)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        elif text_input is not None and text_input.strip():
            text = text_input
        else:
            raise HTTPException(status_code=400, detail="必須提供 file 或 text_input")

        if len(text) > MAX_QA_EXTRACT_TEXT_LENGTH:
            raise HTTPException(status_code=400, detail="text_too_long")

        job_id = _create_pending_job(
            config,
            category_id=category_id,
            topic_id=_build_merged_topic_id(category_id, topic_id),
            category_label=category_label,
            topic_label=topic_label,
            language=language,
        )
        run_job = _required(config.run_extract_job_from_text, "run_extract_job_from_text")
        background_tasks.add_task(run_job, job_id, text, language)

        return {"job_id": job_id, "status": "pending"}

    @router.get("/qa-extract/{job_id}")
    def check_qa_extraction_status(job_id: str):
        get_job = _required(config.get_job, "get_job")
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="工作不存在或已過期")

        result: dict[str, object] = {
            "job_id": job.job_id,
            "status": job.status,
        }
        if job.status == "done":
            result["qa_pairs"] = job.qa_pairs
        elif job.status == "failed":
            result["error"] = job.error
        return result

    @router.post("/qa-extract/{job_id}/import")
    async def import_extracted_qa(
        job_id: str,
        req: ImportQaRequest,
        background_tasks: BackgroundTasks,
        language: str = "zh",
    ):
        get_job = _required(config.get_job, "get_job")
        delete_job = _required(config.delete_job, "delete_job")
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="工作不存在或已過期")

        if not req.qa_pairs:
            raise HTTPException(status_code=400, detail="qa_pairs 陣列不可為空")

        csv_bytes = _qa_pairs_to_csv_bytes(req.qa_pairs)
        filename = f"extracted-{int(time.time())}.csv"
        result = save_qa_csv_to_topic(
            config=config,
            background_tasks=background_tasks,
            language=language,
            csv_bytes=csv_bytes,
            filename=filename,
            content_type="text/csv",
            editable=True,
            topic_id=job.topic_id,
            category_label=job.category_label,
            topic_label=job.topic_label,
            hidden_questions=_hidden_questions_for_import(req),
        )

        delete_job(job_id)

        return {
            "imported_count": result.get("imported_count", 0),
            "filename": result["name"],
            "topic_synced": result["topic_synced"],
            "skipped_all_duplicates": result.get("skipped_all_duplicates", False),
        }


def build_qa_kb_router(
    config: QaKbRouterConfig,
    *,
    include_knowledge: bool = True,
    include_extract: bool = True,
) -> APIRouter:
    router = APIRouter(tags=[config.tag], dependencies=[Depends(config.auth_dep)])
    if include_knowledge:
        _add_knowledge_routes(router, config)
    if include_extract:
        _add_extract_routes(router, config)
    return router
