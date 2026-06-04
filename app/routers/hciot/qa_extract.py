"""HCIoT document-to-Q&A extraction API."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.routers._shared.qa_kb_router import (
    MAX_QA_EXTRACT_FILE_SIZE_BYTES,
    MAX_QA_EXTRACT_TEXT_LENGTH,
    SUPPORTED_EXTRACT_EXTENSIONS,
    ImportQaRequest,
    QaKbRouterConfig,
    QaPairImport,
    build_qa_kb_router,
    run_extract_job_from_text,
)
from app.routers.hciot import knowledge as hciot_knowledge
from app.routers.knowledge_utils import extract_docx_text, safe_filename, xlsx_to_csv_bytes
from app.services.hciot.agent_prompts import get_active_persona_and_role_scope
from app.services.hciot.qa_extract_jobs import create_job, delete_job, get_job, update_job
from app.services.hciot.qa_extractor import extract_qa_from_document
from app.utils import get_other_language


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


def _make_config() -> QaKbRouterConfig:
    return QaKbRouterConfig(
        tag="HCIoT Knowledge",
        app="hciot",
        knowledge_store_factory=lambda: hciot_knowledge.get_hciot_knowledge_store(),
        topic_store_factory=lambda language: hciot_knowledge.get_hciot_topic_store(language),
        rag_source_type="hciot",
        invalidate_cache=lambda language=None: hciot_knowledge.invalidate_hciot_file_map(language),
        other_language=get_other_language,
        extract_text_from_upload=lambda file_bytes, filename: _extract_text_from_upload(file_bytes, filename),
        run_extract_job_from_text=_run_extract_job_from_text,
        create_job=lambda **kwargs: create_job(**kwargs),
        get_job=lambda job_id: get_job(job_id),
        update_job=lambda job_id, **fields: update_job(job_id, **fields),
        delete_job=lambda job_id: delete_job(job_id),
        persona_loader=lambda language: get_active_persona_and_role_scope(language),
        qa_extractor=lambda **kwargs: extract_qa_from_document(**kwargs),
    )


async def _run_extract_job_from_text(job_id: str, text: str, language: str) -> None:
    await run_extract_job_from_text(_make_config(), job_id, text, language)


router = build_qa_kb_router(_make_config(), include_knowledge=False, include_extract=True)
