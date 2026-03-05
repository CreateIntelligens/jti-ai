"""
JTI Quiz API — quiz start and pause endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.auth import verify_auth
from app.models.session import SessionStep
from app.schemas.chat import ChatResponse
from app.services.jti.quiz_helpers import (
    _get_or_rebuild_session,
    _pause_quiz_and_respond,
)
from app.services.jti.runtime_quiz_flow import execute_quiz_start
from app.services.session.session_manager_factory import get_session_manager

session_manager = get_session_manager()
logger = logging.getLogger(__name__)

router = APIRouter(tags=["JTI Quiz"])


class QuizActionRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")


@router.post("/quiz/start")
async def quiz_start(request: QuizActionRequest, auth: dict = Depends(verify_auth)):
    """直接開始測驗（不依賴自然語言判斷）"""
    try:
        s = session_manager.get_session(request.session_id)
        if s and s.step.value == "DONE":
            s.step = SessionStep.WELCOME
            session_manager.update_session(s)
        return await execute_quiz_start(request.session_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz/pause")
async def quiz_pause(request: QuizActionRequest, auth: dict = Depends(verify_auth)):
    """直接暫停測驗（不依賴自然語言判斷）"""
    try:
        session = _get_or_rebuild_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return ChatResponse(**(await _pause_quiz_and_respond(
            session_id=request.session_id,
            log_user_message="[API] quiz_pause",
            session=session,
        )))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quiz_pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
