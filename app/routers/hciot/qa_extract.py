"""HCIoT document-to-Q&A extraction API."""

import csv
import io
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth import verify_admin
from app.routers.hciot.knowledge import (
    _build_merged_topic_id,
    save_qa_csv_to_topic,
)
from app.routers.knowledge_utils import extract_docx_text, safe_filename, xlsx_to_csv_bytes
from app.services.hciot.agent_prompts import get_active_persona_and_role_scope
from app.services.hciot.qa_extract_jobs import create_job, delete_job, get_job, update_job
from app.services.hciot.qa_extractor import extract_qa_from_document

logger = logging.getLogger(__name__)

router = APIRouter(tags=["HCIoT Knowledge"], dependencies=[Depends(verify_admin)])

SUPPORTED_EXTRACT_EXTENSIONS = {".docx", ".txt", ".md", ".csv", ".xlsx"}
MAX_QA_EXTRACT_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_QA_EXTRACT_TEXT_LENGTH = 30000


class QaPairImport(BaseModel):
    q: str
    a: str


class ImportQaRequest(BaseModel):
    qa_pairs: list[QaPairImport]
    hidden_questions: list[str] | None = None


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


async def _run_extract_job_from_text(job_id: str, text: str, language: str) -> None:
    try:
        update_job(job_id, status="running")
        persona_text, role_scope_text = get_active_persona_and_role_scope(language)
        qa_pairs = await extract_qa_from_document(
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
    *,
    category_id: str | None,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
    language: str,
) -> str:
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
            text = _extract_text_from_upload(file_bytes, safe_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif text_input is not None and text_input.strip():
        text = text_input
    else:
        raise HTTPException(status_code=400, detail="必須提供 file 或 text_input")

    if len(text) > MAX_QA_EXTRACT_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail="text_too_long")

    job_id = _create_pending_job(
        category_id=category_id,
        topic_id=_build_merged_topic_id(category_id, topic_id),
        category_label=category_label,
        topic_label=topic_label,
        language=language,
    )
    background_tasks.add_task(_run_extract_job_from_text, job_id, text, language)

    return {"job_id": job_id, "status": "pending"}


@router.get("/qa-extract/{job_id}")
def check_qa_extraction_status(job_id: str):
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
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="工作不存在或已過期")

    if not req.qa_pairs:
        raise HTTPException(status_code=400, detail="qa_pairs 陣列不可為空")

    csv_bytes = _qa_pairs_to_csv_bytes(req.qa_pairs)
    filename = f"extracted-{int(time.time())}.csv"
    result = save_qa_csv_to_topic(
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
