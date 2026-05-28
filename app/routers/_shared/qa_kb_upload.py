"""Upload and write helpers for QA knowledge-base workspaces."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from app.routers.knowledge_utils import (
    delete_from_rag,
    extract_docx_text,
    sync_to_rag,
    xlsx_to_csv_bytes,
)
from app.routers._shared.qa_kb_sync import (
    _existing_topic_questions,
    _sync_topic_questions_from_store,
)
from app.services._shared.qa_kb.csv_utils import (
    UnsupportedQaCsvError,
    extract_questions_from_csv,
    normalize_qa_csv_rows,
    split_qa_csv_by_image,
    validate_supported_hciot_csv,
)

if TYPE_CHECKING:
    from app.routers._shared.qa_kb_router import (
        ImportQaRequest,
        QaKbRouterConfig,
        QaPairImport,
    )

logger = logging.getLogger(__name__)


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


def _required(value: Any, name: str) -> Any:
    if value is None:
        raise RuntimeError(f"QaKbRouterConfig.{name} is required for this route")
    return value


def _prepare_csv_bytes(file_bytes: bytes) -> bytes:
    try:
        validate_supported_hciot_csv(file_bytes)
    except UnsupportedQaCsvError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return normalize_qa_csv_rows(file_bytes) or file_bytes


def _fallback_upload_error_response(detail: object) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": detail,
            "error_code": "unrecognized_format",
            "can_fallback_to_ai": True,
        },
    )


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
