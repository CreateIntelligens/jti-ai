"""ESG explicit quiz actions."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_auth
from app.services.esg.quiz_flow import ESG_QUIZ_CONFIG
from app.services.general.managed_quiz import ManagedQuizService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ESG Quiz"], dependencies=[Depends(verify_auth)])
quiz_service = ManagedQuizService(ESG_QUIZ_CONFIG)


class QuizActionRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")


@router.post("/quiz/start")
async def quiz_start(request: QuizActionRequest):
    try:
        return await quiz_service.start(request.session_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ESG quiz_start failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/quiz/pause")
async def quiz_pause(request: QuizActionRequest):
    try:
        return await quiz_service.pause(request.session_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ESG quiz_pause failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
