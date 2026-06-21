"""
JTI Quiz API — quiz start and pause endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.auth import require_app_access
from app.services.general.managed_quiz import ManagedQuizService
from app.services.jti.quiz_flow import JTI_QUIZ_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter(tags=["JTI Quiz"], dependencies=[Depends(require_app_access("jti"))])


quiz_service = ManagedQuizService(JTI_QUIZ_CONFIG)


class QuizActionRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")


@router.post("/quiz/start")
async def quiz_start(request: QuizActionRequest):
    """直接開始測驗（不依賴自然語言判斷）"""
    try:
        return await quiz_service.start(request.session_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/pause")
async def quiz_pause(request: QuizActionRequest):
    """直接暫停測驗（不依賴自然語言判斷）"""
    try:
        return await quiz_service.pause(request.session_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
