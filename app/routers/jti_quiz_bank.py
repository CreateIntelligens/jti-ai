"""
Quiz Bank CRUD API Router.

Provides endpoints for managing quiz banks (multi-set, max 3), questions,
metadata, color results, and CSV/XLSX import/export.
"""

from __future__ import annotations

import csv
import io
import logging
import urllib.parse
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import verify_auth
from app.services.quiz_bank_store import get_quiz_bank_store, DEFAULT_BANK_ID
from app.services.color_results_store import get_color_results_store
from app.tools.quiz import invalidate_quiz_cache
from app.tools.color_results import invalidate_color_results_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jti/quiz-bank", tags=["jti-quiz-bank"])


# ========== Request Models ==========


class QuestionOption(BaseModel):
    id: str
    text: str
    score: dict[str, int | float]


class CreateQuestionRequest(BaseModel):
    id: str
    text: str
    category: str
    weight: int | float = 1
    options: list[QuestionOption]


class UpdateQuestionRequest(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    weight: Optional[int | float] = None
    options: Optional[list[QuestionOption]] = None


class UpdateMetadataRequest(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    total_questions: Optional[int] = None
    dimensions: Optional[list[str]] = None
    tie_breaker_priority: Optional[list[str]] = None
    selection_rules: Optional[dict] = None


class UpdateColorResultRequest(BaseModel):
    title: Optional[str] = None
    color_name: Optional[str] = None
    recommended_colors: Optional[list[str]] = None
    description: Optional[str] = None


class CreateBankRequest(BaseModel):
    name: str


# ========== Bank Management ==========


@router.get("/banks/")
def list_banks(
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """List all quiz banks for a language (max 3)."""
    store = get_quiz_bank_store()
    banks = store.list_banks(language)
    return {"banks": banks, "total": len(banks), "max": 3}


@router.post("/banks/", status_code=201)
def create_bank(
    request: CreateBankRequest,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Create a new empty quiz bank."""
    store = get_quiz_bank_store()
    try:
        bank = store.create_bank(language, request.name)
        return bank
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/banks/{bank_id}")
def delete_bank(
    bank_id: str,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Delete a quiz bank and all its questions."""
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot delete default bank")
    store = get_quiz_bank_store()
    try:
        deleted = store.delete_bank(language, bank_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")
        invalidate_quiz_cache(language)
        return {"message": f"Bank '{bank_id}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/banks/{bank_id}/activate")
def activate_bank(
    bank_id: str,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Set a bank as active."""
    store = get_quiz_bank_store()
    success = store.set_active_bank(language, bank_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")
    invalidate_quiz_cache(language)
    return {"message": f"Bank '{bank_id}' is now active"}


# ========== Question Endpoints ==========


@router.get("/questions/")
def list_questions(
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    category: Optional[str] = Query(None),
    auth: dict = Depends(verify_auth),
):
    """List quiz questions for a bank."""
    store = get_quiz_bank_store()
    questions = store.list_questions(language, bank_id, category)
    return {"questions": questions, "total": len(questions)}


@router.get("/questions/{question_id}")
def get_question(
    question_id: str,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Get a single question."""
    store = get_quiz_bank_store()
    question = store.get_question(language, bank_id, question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found")
    return question


@router.post("/questions/", status_code=201)
def create_question(
    request: CreateQuestionRequest,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Create a new question in a bank."""
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    existing = store.get_question(language, bank_id, request.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Question '{request.id}' already exists")

    result = store.create_question(language, bank_id, request.model_dump())
    invalidate_quiz_cache(language)
    return result


@router.put("/questions/{question_id}")
def update_question(
    question_id: str,
    request: UpdateQuestionRequest,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Update an existing question."""
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = store.update_question(language, bank_id, question_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found")
    invalidate_quiz_cache(language)
    return result


@router.delete("/questions/{question_id}")
def delete_question(
    question_id: str,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Delete a question."""
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    deleted = store.delete_question(language, bank_id, question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found")
    invalidate_quiz_cache(language)
    return {"message": f"Question '{question_id}' deleted"}


# ========== Metadata Endpoints ==========


@router.get("/metadata/")
def get_metadata(
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Get quiz bank metadata."""
    store = get_quiz_bank_store()
    meta = store.get_metadata(language, bank_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Metadata not found")
    return meta


@router.put("/metadata/")
def update_metadata(
    request: UpdateMetadataRequest,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Update quiz bank metadata."""
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = store.upsert_metadata(language, bank_id, update_data)
    invalidate_quiz_cache(language)
    return result


# ========== Color Results Endpoints ==========


@router.get("/color-results/")
def list_color_results(
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """List all color results."""
    store = get_color_results_store()
    results = store.list_results(language)
    return {"results": results, "total": len(results)}


@router.put("/color-results/{color_id}")
def update_color_result(
    color_id: str,
    request: UpdateColorResultRequest,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Update a color result."""
    store = get_color_results_store()
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = store.upsert_result(language, color_id, update_data)
    invalidate_color_results_cache(language)
    return result


@router.get("/color-results/export/")
def export_color_results(
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Export color results as CSV download."""
    store = get_color_results_store()
    results = store.list_results(language)

    output = io.StringIO()
    output.write('\ufeff')  # Write UTF-8 BOM for Excel compatibility
    headers = ["color_id", "color_name", "title", "recommended_colors", "description"]
    
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    for cr in results:
        row: dict[str, str] = {
            "color_id": cr.get("color_id", ""),
            "color_name": cr.get("color_name", ""),
            "title": cr.get("title", ""),
            "recommended_colors": ", ".join(cr.get("recommended_colors", [])),
            "description": cr.get("description", ""),
        }
        writer.writerow(row)

    output.seek(0)

    filename = f"color_results_{language}.csv"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
        },
    )


# ========== Stats Endpoint ==========


@router.get("/stats/")
def get_stats(
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Get quiz bank statistics."""
    store = get_quiz_bank_store()
    questions = store.list_questions(language, bank_id)
    meta = store.get_metadata(language, bank_id)

    category_counts: dict[str, int] = {}
    for q in questions:
        cat = q.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "total_questions": len(questions),
        "categories": category_counts,
        "dimensions": meta.get("dimensions", []) if meta else [],
        "selection_rules": meta.get("selection_rules", {}) if meta else {},
    }


# ========== CSV/XLSX Import ==========


def _parse_scores(s: str) -> dict[str, float]:
    """Parse compact score string like 'metal:2,cool:1'."""
    result = {}
    for pair in s.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        key, val = pair.split(":", 1)
        try:
            result[key.strip()] = float(val.strip())
        except ValueError:
            pass
    return result


def _parse_csv_rows(reader) -> list[dict]:
    """Parse CSV rows into question dicts."""
    questions = []
    for row in reader:
        if not row.get("id") or not row.get("text"):
            continue

        options = []
        # Support up to 5 options (a through e)
        for letter in "abcde":
            opt_id = row.get(f"option_{letter}_id", "").strip()
            opt_text = row.get(f"option_{letter}_text", "").strip()
            opt_scores = row.get(f"option_{letter}_scores", "").strip()
            if opt_id and opt_text:
                options.append({
                    "id": opt_id,
                    "text": opt_text,
                    "score": _parse_scores(opt_scores),
                })

        if len(options) < 2:
            continue

        question: dict[str, Any] = {
            "id": row["id"].strip(),
            "text": row["text"].strip(),
            "category": row.get("category", "personality").strip(),
            "weight": float(row.get("weight", "1") or "1"),
            "options": options,
        }
        questions.append(question)
    return questions


@router.post("/import/")
async def import_questions(
    file: UploadFile = File(...),
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    replace: bool = Query(False, description="Replace all existing questions"),
    auth: dict = Depends(verify_auth),
):
    """Import questions from CSV or XLSX file."""
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()

    # Check bank exists
    meta = store.get_metadata(language, bank_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")

    data = await file.read()
    filename = (file.filename or "").lower()

    questions: list[dict] = []

    if filename.endswith(".csv"):
        text = data.decode("utf-8-sig")  # Handle BOM
        reader = csv.DictReader(io.StringIO(text))
        questions = _parse_csv_rows(reader)

    elif filename.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(status_code=500, detail="openpyxl not installed, XLSX not supported")

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        ws = wb.active
        if ws is None:
            raise HTTPException(status_code=400, detail="Empty workbook")

        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            raise HTTPException(status_code=400, detail="No data rows")

        headers = [str(h or "").strip().lower() for h in rows[0]]
        dict_rows = [dict(zip(headers, [str(c or "").strip() for c in row])) for row in rows[1:]]
        questions = _parse_csv_rows(iter(dict_rows))
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .csv or .xlsx")

    if not questions:
        raise HTTPException(status_code=400, detail="No valid questions found in file")

    if replace:
        count = store.replace_all_questions(language, bank_id, questions)
    else:
        count = store.bulk_upsert_questions(language, bank_id, questions)

    invalidate_quiz_cache(language)
    return {"message": f"Imported {count} questions", "count": count}


# ========== CSV Export ==========


@router.get("/export/")
def export_questions(
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Export questions as CSV download."""
    store = get_quiz_bank_store()
    questions = store.list_questions(language, bank_id)

    output = io.StringIO()
    output.write('\ufeff')  # Write UTF-8 BOM for Excel compatibility
    # Build headers dynamically based on max options
    max_opts = max((len(q.get("options", [])) for q in questions), default=2)
    max_opts = max(max_opts, 2)

    headers = ["id", "text", "category", "weight"]
    for i, letter in enumerate("abcde"[:max_opts]):
        headers.extend([f"option_{letter}_id", f"option_{letter}_text", f"option_{letter}_scores"])

    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    for q in questions:
        row: dict[str, str] = {
            "id": q.get("id", ""),
            "text": q.get("text", ""),
            "category": q.get("category", ""),
            "weight": str(q.get("weight", 1)),
        }
        for i, opt in enumerate(q.get("options", [])):
            letter = "abcde"[i]
            row[f"option_{letter}_id"] = opt.get("id", "")
            row[f"option_{letter}_text"] = opt.get("text", "")
            scores = opt.get("score", {})
            row[f"option_{letter}_scores"] = ",".join(f"{k}:{v}" for k, v in scores.items())
        writer.writerow(row)

    output.seek(0)
    meta = store.get_metadata(language, bank_id)
    bank_name = meta.get("name", bank_id) if meta else bank_id

    # URL-encode the filename to support non-ASCII characters (e.g., Chinese)
    filename = f"quiz_bank_{bank_name}_{language}.csv"
    encoded_filename = urllib.parse.quote(filename)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
        },
    )
