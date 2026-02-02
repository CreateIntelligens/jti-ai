"""
MBTI 遊戲 API Endpoints
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
from app.services.session_manager import session_manager
from app.services.main_agent import main_agent
from app.models.session import GameMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mbti", tags=["MBTI Game"])


# === Request/Response Models ===

class CreateSessionRequest(BaseModel):
    """建立 session 請求"""
    mode: GameMode = GameMode.MBTI


class CreateSessionResponse(BaseModel):
    """建立 session 回應"""
    session_id: str
    mode: str
    step: str
    message: str = "測驗已準備好，隨時可以開始！"


class ChatRequest(BaseModel):
    """對話請求"""
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="使用者訊息")
    store_id: Optional[str] = Field(None, description="File Search Store ID（選用）")


class ChatResponse(BaseModel):
    """對話回應"""
    message: str
    session: Optional[Dict[str, Any]] = None
    tool_calls: Optional[list] = None
    error: Optional[str] = None


class GetSessionResponse(BaseModel):
    """取得 session 回應"""
    session: Dict[str, Any]


# === Endpoints ===

@router.post("/session/new", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    建立新的測驗 session

    這會初始化一個新的 MBTI 測驗流程
    """
    try:
        session = session_manager.create_session(mode=request.mode)

        logger.info(f"Created new session: {session.session_id}")

        return CreateSessionResponse(
            session_id=session.session_id,
            mode=session.mode.value,
            step=session.step.value,
            message="測驗已準備好，請說「開始測驗」來開始！"
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=GetSessionResponse)
async def get_session(session_id: str):
    """
    取得 session 狀態

    查詢目前測驗的進度和結果
    """
    try:
        session = session_manager.get_session(session_id)

        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return GetSessionResponse(
            session=session.model_dump()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    主要對話端點

    處理使用者訊息，包含：
    - 開始測驗
    - 回答問題
    - 查看結果
    - 詢問商品
    """
    try:
        result = await main_agent.chat(
            session_id=request.session_id,
            user_message=request.message,
            store_id=request.store_id
        )

        return ChatResponse(**result)

    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    刪除 session

    清除測驗記錄
    """
    try:
        success = session_manager.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """
    列出所有 sessions（測試用）
    """
    try:
        sessions = session_manager.get_all_sessions()
        return {
            "sessions": [s.model_dump() for s in sessions],
            "total": len(sessions)
        }

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
