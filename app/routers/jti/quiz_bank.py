"""JTI quiz-bank URL compatibility adapter over General handlers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile

from app.auth import require_app_access, verify_auth
from app.routers.general import quiz_bank as general_quiz_bank
from app.services.quiz.config import JTI_STORE_NAME


CreateBankRequest = general_quiz_bank.CreateBankRequest
CreateQuestionRequest = general_quiz_bank.CreateQuestionRequest
CreateQuizSetRequest = general_quiz_bank.CreateQuizSetRequest
UpdateQuestionRequest = general_quiz_bank.UpdateQuestionRequest
UpdateQuizResultRequest = general_quiz_bank.UpdateQuizResultRequest
DEFAULT_BANK_ID = general_quiz_bank.DEFAULT_BANK_ID

router = APIRouter(tags=["JTI Quiz Bank"], dependencies=[Depends(require_app_access("jti"))])


@router.get("/banks/")
def list_banks(
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.list_banks(
        JTI_STORE_NAME,
        request,
        language,
        auth,
    )


@router.post("/banks/", status_code=201)
def create_bank(
    request_data: CreateBankRequest,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.create_bank(
        JTI_STORE_NAME,
        request_data,
        request,
        language,
        auth,
    )


@router.delete("/banks/{bank_id}")
def delete_bank(
    bank_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.delete_bank(
        JTI_STORE_NAME,
        bank_id,
        request,
        language,
        auth,
    )


@router.post("/banks/{bank_id}/activate")
def activate_bank(
    bank_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.activate_bank(
        JTI_STORE_NAME,
        bank_id,
        request,
        language,
        auth,
    )


@router.get("/questions/")
def list_questions(
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.list_questions(
        JTI_STORE_NAME,
        request,
        language,
        bank_id,
        auth,
    )


@router.post("/questions/", status_code=201)
def create_question(
    request_data: CreateQuestionRequest,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.create_question(
        JTI_STORE_NAME,
        request_data,
        request,
        language,
        bank_id,
        auth,
    )


@router.put("/questions/{question_id}")
def update_question(
    question_id: str,
    request_data: UpdateQuestionRequest,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.update_question(
        JTI_STORE_NAME,
        question_id,
        request_data,
        request,
        language,
        bank_id,
        auth,
    )


@router.delete("/questions/{question_id}")
def delete_question(
    question_id: str,
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.delete_question(
        JTI_STORE_NAME,
        question_id,
        request,
        language,
        bank_id,
        auth,
    )


@router.get("/quiz-results/sets/")
def list_quiz_sets(
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.list_quiz_sets(
        JTI_STORE_NAME,
        request,
        language,
        auth,
    )


@router.post("/quiz-results/sets/", status_code=201)
def create_quiz_set(
    request_data: CreateQuizSetRequest,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.create_quiz_set(
        JTI_STORE_NAME,
        request_data,
        request,
        language,
        auth,
    )


@router.delete("/quiz-results/sets/{set_id}")
def delete_quiz_set(
    set_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.delete_quiz_set(
        JTI_STORE_NAME,
        set_id,
        request,
        language,
        auth,
    )


@router.post("/quiz-results/sets/{set_id}/activate")
def activate_quiz_set(
    set_id: str,
    request: Request,
    language: str = Query("zh"),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.activate_quiz_set(
        JTI_STORE_NAME,
        set_id,
        request,
        language,
        auth,
    )


@router.get("/quiz-results/")
def list_quiz_results(
    request: Request,
    language: str = Query("zh"),
    set_id: str | None = Query(None),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.list_quiz_results(
        JTI_STORE_NAME,
        request,
        language,
        set_id,
        auth,
    )


@router.put("/quiz-results/{quiz_id}")
def update_quiz_result(
    quiz_id: str,
    request_data: UpdateQuizResultRequest,
    request: Request,
    language: str = Query("zh"),
    set_id: str | None = Query(None),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.update_quiz_result(
        JTI_STORE_NAME,
        quiz_id,
        request_data,
        request,
        language,
        set_id,
        auth,
    )


@router.get("/stats/")
def get_stats(
    request: Request,
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.get_stats(
        JTI_STORE_NAME,
        request,
        language,
        bank_id,
        auth,
    )


@router.post("/transfer/import")
async def import_data(
    request: Request,
    file: UploadFile = File(...),
    type: str = Query("questions", description="'questions' or 'results'"),
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    replace: bool = Query(False, description="Replace all existing data"),
    auth: dict = Depends(verify_auth),
):
    return await general_quiz_bank.import_data(
        JTI_STORE_NAME,
        request,
        file,
        type,
        language,
        bank_id,
        replace,
        auth,
    )


@router.get("/transfer/export")
def export_data(
    request: Request,
    type: str = Query("questions", description="'questions' or 'results'"),
    language: str = Query("zh"),
    bank_id: str = Query(DEFAULT_BANK_ID),
    auth: dict = Depends(verify_auth),
):
    return general_quiz_bank.export_data(
        JTI_STORE_NAME,
        request,
        type,
        language,
        bank_id,
        auth,
    )
