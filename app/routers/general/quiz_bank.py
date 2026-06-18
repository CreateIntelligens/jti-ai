"""
Quiz Bank CRUD API Router for general stores.

Provides endpoints for managing quiz banks (multi-set, max 3), questions,
metadata, quiz results, and CSV/XLSX import/export for general stores.
"""

from __future__ import annotations

import csv
import io
import logging
import urllib.parse
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import verify_auth
from app.routers.general.stores import _authorize_store_access
from app.services.jti.quiz_bank_store import get_quiz_bank_store, DEFAULT_BANK_ID
from app.services.jti.quiz_results_store import get_quiz_results_store, DEFAULT_SET_ID
from app.tools.jti.quiz import invalidate_quiz_cache
from app.tools.jti.quiz_results import invalidate_quiz_results_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/general/quiz-bank/{store_name}", tags=["General Store Quiz Bank"])


# ========== Request Models ==========


class QuestionOption(BaseModel):
    id: str
    text: str
    score: dict[str, int | float]


class CreateQuestionRequest(BaseModel):
    id: str
    text: str
    weight: int | float = 1
    options: list[QuestionOption]


class UpdateQuestionRequest(BaseModel):
    text: Optional[str] = None
    weight: Optional[int | float] = None
    options: Optional[list[QuestionOption]] = None


class UpdateBankRequest(BaseModel):
    """Update bank metadata fields."""
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    total_questions: Optional[int] = None
    dimensions: Optional[list[str]] = None
    tie_breaker_priority: Optional[list[str]] = None
    selection_rules: Optional[dict] = None


class UpdateQuizResultRequest(BaseModel):
    title: Optional[str] = None
    color_name: Optional[str] = None
    recommended_colors: Optional[list[str]] = None
    description: Optional[str] = None


class CreateBankRequest(BaseModel):
    name: str


class CreateQuizSetRequest(BaseModel):
    name: str


# ========== Bank Endpoints ==========


@router.get("/banks/")
def list_banks(
    store_name: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """List all quiz banks for a language (max 3)."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    banks = store.list_banks(language, store_name=store_name)
    return {"banks": banks, "total": len(banks), "max": 3}


@router.post("/banks/", status_code=201)
def create_bank(
    store_name: str,
    request_data: CreateBankRequest,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Create a new quiz bank for the store."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    try:
        bank = store.create_bank(language, request_data.name, store_name=store_name, clone_default=False)
        return bank
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/banks/{bank_id}")
def get_bank(
    store_name: str,
    bank_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Get a bank's metadata."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    meta = store.get_metadata(language, bank_id, store_name=store_name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")
    return meta


@router.patch("/banks/{bank_id}")
def update_bank(
    store_name: str,
    bank_id: str,
    request_data: UpdateBankRequest,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Update a bank's metadata."""
    _authorize_store_access(store_name, request, auth)
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    update_data = request_data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = store.upsert_metadata(language, bank_id, update_data, store_name=store_name)
    invalidate_quiz_cache(language, store_name=store_name)
    return result


@router.delete("/banks/{bank_id}")
def delete_bank(
    store_name: str,
    bank_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Delete a quiz bank and all its questions."""
    _authorize_store_access(store_name, request, auth)
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot delete default bank")
    store = get_quiz_bank_store()
    try:
        deleted = store.delete_bank(language, bank_id, store_name=store_name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")
        invalidate_quiz_cache(language, store_name=store_name)
        return {"message": f"Bank '{bank_id}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/banks/{bank_id}/activate")
def activate_bank(
    store_name: str,
    bank_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Set a bank as active."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    success = store.set_active_bank(language, bank_id, store_name=store_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")
    invalidate_quiz_cache(language, store_name=store_name)
    return {"message": f"Bank '{bank_id}' is now active"}


# ========== Question Endpoints ==========


@router.get("/questions/")
def list_questions(
    store_name: str,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """List quiz questions for a bank."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    questions = store.list_questions(language, bank_id, store_name=store_name)
    return {"questions": questions, "total": len(questions)}


@router.get("/questions/{question_id}")
def get_question(
    store_name: str,
    question_id: str,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Get a single question."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    question = store.get_question(language, bank_id, question_id, store_name=store_name)
    if not question:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found")
    return question


@router.post("/questions/", status_code=201)
def create_question(
    store_name: str,
    request_data: CreateQuestionRequest,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Create a new question in a bank."""
    _authorize_store_access(store_name, request, auth)
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    existing = store.get_question(language, bank_id, request_data.id, store_name=store_name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Question '{request_data.id}' already exists")
    result = store.create_question(language, bank_id, request_data.model_dump(), store_name=store_name)
    invalidate_quiz_cache(language, store_name=store_name)
    return result


@router.put("/questions/{question_id}")
def update_question(
    store_name: str,
    question_id: str,
    request_data: UpdateQuestionRequest,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Update an existing question."""
    _authorize_store_access(store_name, request, auth)
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    update_data = request_data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = store.update_question(language, bank_id, question_id, update_data, store_name=store_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found")
    invalidate_quiz_cache(language, store_name=store_name)
    return result


@router.delete("/questions/{question_id}")
def delete_question(
    store_name: str,
    question_id: str,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Delete a question."""
    _authorize_store_access(store_name, request, auth)
    if bank_id == DEFAULT_BANK_ID:
        raise HTTPException(status_code=403, detail="Cannot modify default bank")
    store = get_quiz_bank_store()
    deleted = store.delete_question(language, bank_id, question_id, store_name=store_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found")
    invalidate_quiz_cache(language, store_name=store_name)
    return {"message": f"Question '{question_id}' deleted"}


# ========== Quiz Result Set Endpoints ==========


@router.get("/quiz-results/sets/")
def list_quiz_sets(
    store_name: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """List all quiz result sets for a language."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_results_store()
    sets = store.list_sets(language, store_name=store_name)
    return {"sets": sets, "total": len(sets), "max": 3}


@router.post("/quiz-results/sets/", status_code=201)
def create_quiz_set(
    store_name: str,
    request_data: CreateQuizSetRequest,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Create a new quiz result set copied from the default set."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_results_store()
    try:
        quiz_set = store.create_set(language, request_data.name, store_name=store_name)
        return quiz_set
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/quiz-results/sets/{set_id}")
def delete_quiz_set(
    store_name: str,
    set_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Delete a quiz result set."""
    _authorize_store_access(store_name, request, auth)
    if set_id == DEFAULT_SET_ID:
        raise HTTPException(status_code=403, detail="Cannot delete default set")
    store = get_quiz_results_store()
    try:
        deleted = store.delete_set(language, set_id, store_name=store_name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")
        invalidate_quiz_results_cache(language, store_name=store_name)
        return {"message": f"Set '{set_id}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/quiz-results/sets/{set_id}/activate")
def activate_quiz_set(
    store_name: str,
    set_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    """Set a quiz result set as active."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_results_store()
    success = store.set_active(language, set_id, store_name=store_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")
    invalidate_quiz_results_cache(language, store_name=store_name)
    return {"message": f"Set '{set_id}' is now active"}


# ========== Quiz Results Endpoints ==========


@router.get("/quiz-results/")
def list_quiz_results(
    store_name: str,
    request: Request,
    language: str = Query("zh"),
    set_id: Optional[str] = Query(None),
    auth: dict = Depends(verify_auth),
):
    """List all quiz results for a set (defaults to the active set)."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_results_store()
    results = store.list_results(language, set_id, store_name=store_name)
    return {"results": results, "total": len(results)}


@router.put("/quiz-results/{quiz_id}")
def update_quiz_result(
    store_name: str,
    quiz_id: str,
    request_data: UpdateQuizResultRequest,
    request: Request,
    language: str = Query("zh"),
    set_id: Optional[str] = Query(None),
    auth: dict = Depends(verify_auth),
):
    """Update a quiz result."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_results_store()
    resolved_set_id = set_id if set_id else store.get_active_set_id(language, store_name=store_name)
    if resolved_set_id == DEFAULT_SET_ID:
        raise HTTPException(status_code=400, detail="Cannot modify default set")
    update_data = request_data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = store.upsert_result(language, quiz_id, update_data, set_id=resolved_set_id, store_name=store_name)
    invalidate_quiz_results_cache(language, store_name=store_name)
    return result


# ========== Stats Endpoint ==========


@router.get("/stats/")
def get_stats(
    store_name: str,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Get quiz bank statistics."""
    _authorize_store_access(store_name, request, auth)
    store = get_quiz_bank_store()
    questions = store.list_questions(language, bank_id, store_name=store_name)
    meta = store.get_metadata(language, bank_id, store_name=store_name)

    return {
        "total_questions": len(questions),
        "categories": {},
        "dimensions": meta.get("dimensions", []) if meta else [],
        "selection_rules": meta.get("selection_rules", {}) if meta else {},
    }


# ========== Import/Export (unified) ==========


def _parse_scores(s: str) -> dict[str, float]:
    """Parse compact score string like 'analyst:2,guardian:1'."""
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

        questions.append({
            "id": row["id"].strip(),
            "text": row["text"].strip(),
            "weight": float(row.get("weight", "1") or "1"),
            "options": options,
        })
    return questions


@router.post("/transfer/import")
async def import_data(
    store_name: str,
    request: Request,
    file: UploadFile = File(...),
    type: str = Query("questions", description="'questions' or 'results'"),
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    replace: bool = Query(False, description="Replace all existing data"),
    auth: dict = Depends(verify_auth),
):
    """Import questions or quiz results from CSV/XLSX file."""
    _authorize_store_access(store_name, request, auth)
    normalized_type = "results" if type in {"results", "colors"} else type
    if normalized_type not in ("questions", "results"):
        raise HTTPException(status_code=400, detail="type must be 'questions' or 'results'")

    data = await file.read()
    filename = (file.filename or "").lower()

    if normalized_type == "questions":
        if bank_id == DEFAULT_BANK_ID:
            raise HTTPException(status_code=403, detail="Cannot modify default bank")
        store = get_quiz_bank_store()
        meta = store.get_metadata(language, bank_id, store_name=store_name)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found")

        if filename.endswith(".csv"):
            text = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            questions = _parse_csv_rows(reader)
        elif filename.endswith((".xlsx", ".xls")):
            try:
                import openpyxl
            except ImportError:
                raise HTTPException(status_code=500, detail="openpyxl not installed")
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

        count = store.replace_all_questions(language, bank_id, questions, store_name=store_name) if replace else store.bulk_upsert_questions(language, bank_id, questions, store_name=store_name)
        invalidate_quiz_cache(language, store_name=store_name)
        return {"message": f"Imported {count} questions", "count": count}

    else:  # results
        if not filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Quiz results import only supports .csv")
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        quiz_store = get_quiz_results_store()
        count = 0
        for row in reader:
            quiz_id = (row.get("quiz_id") or row.get("color_id") or "").strip()
            if not quiz_id:
                continue
            update_data: dict[str, Any] = {}
            if row.get("color_name"):
                update_data["color_name"] = row["color_name"].strip()
            if row.get("title"):
                update_data["title"] = row["title"].strip()
            if row.get("recommended_colors"):
                update_data["recommended_colors"] = [c.strip() for c in row["recommended_colors"].split(",") if c.strip()]
            if row.get("description"):
                update_data["description"] = row["description"].strip()
            if update_data:
                quiz_store.upsert_result(language, quiz_id, update_data, store_name=store_name)
                count += 1
        invalidate_quiz_results_cache(language, store_name=store_name)
        return {"message": f"Imported {count} quiz results", "count": count}


@router.get("/transfer/export")
def export_data(
    store_name: str,
    request: Request,
    type: str = Query("questions", description="'questions' or 'results'"),
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    """Export questions or quiz results as CSV."""
    _authorize_store_access(store_name, request, auth)
    normalized_type = "results" if type in {"results", "colors"} else type
    if normalized_type not in ("questions", "results"):
        raise HTTPException(status_code=400, detail="type must be 'questions' or 'results'")

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Excel

    if normalized_type == "questions":
        store = get_quiz_bank_store()
        questions = store.list_questions(language, bank_id, store_name=store_name)
        max_opts = max((len(q.get("options", [])) for q in questions), default=2)
        max_opts = max(max_opts, 2)
        headers = ["id", "text", "weight"]
        for letter in "abcde"[:max_opts]:
            headers.extend([f"option_{letter}_id", f"option_{letter}_text", f"option_{letter}_scores"])

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for q in questions:
            row: dict[str, str] = {
                "id": q.get("id", ""),
                "text": q.get("text", ""),
                "weight": str(q.get("weight", 1)),
            }
            for i, opt in enumerate(q.get("options", [])):
                letter = "abcde"[i]
                row[f"option_{letter}_id"] = opt.get("id", "")
                row[f"option_{letter}_text"] = opt.get("text", "")
                scores = opt.get("score", {})
                row[f"option_{letter}_scores"] = ",".join(f"{k}:{v}" for k, v in scores.items())
            writer.writerow(row)

        meta = store.get_metadata(language, bank_id, store_name=store_name)
        bank_name = meta.get("name", bank_id) if meta else bank_id
        filename = f"quiz_bank_{bank_name}_{language}.csv"

    else:  # results
        quiz_store = get_quiz_results_store()
        results = quiz_store.list_results(language, store_name=store_name)  # uses active set
        headers_list = ["quiz_id", "color_name", "title", "recommended_colors", "description"]
        writer = csv.DictWriter(output, fieldnames=headers_list)
        writer.writeheader()
        for quiz_result in results:
            writer.writerow({
                "quiz_id": quiz_result.get("quiz_id", ""),
                "color_name": quiz_result.get("color_name", ""),
                "title": quiz_result.get("title", ""),
                "recommended_colors": ", ".join(quiz_result.get("recommended_colors", [])),
                "description": quiz_result.get("description", ""),
            })
        filename = f"quiz_results_{language}.csv"

    output.seek(0)
    encoded_filename = urllib.parse.quote(filename)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"},
    )
