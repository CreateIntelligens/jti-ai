"""Shared chat and conversation API schemas (used by JTI, HCIoT, General)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    language: str = "zh"
    previous_session_id: Optional[str] = None


class CreateSessionResponse(BaseModel):
    ok: bool = True
    session_id: str
    message: str = "Session created"


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="使用者訊息")
    turn_number: Optional[int] = Field(
        None,
        description="若是重新生成，則指定該訊息的 turn_number（之後的記錄會被刪除）",
    )


class ChatResponse(BaseModel):
    message: str
    tts_text: Optional[str] = None
    session: Optional[Dict[str, Any]] = None
    tool_calls: Optional[list] = None
    turn_number: Optional[int] = None
    error: Optional[str] = None


class ConversationToolCall(BaseModel):
    tool: Optional[str] = None
    tool_name: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: Optional[float] = None
    model_config = ConfigDict(extra="allow")


class ConversationItem(BaseModel):
    mongo_id: Optional[str] = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    session_id: str
    mode: str
    turn_number: Optional[int] = None
    timestamp: str
    responded_at: Optional[str] = None
    user_message: str
    agent_response: str
    tool_calls: List[ConversationToolCall] = Field(default_factory=list)
    session_snapshot: Optional[Dict[str, Any]] = None
    session_state: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ConversationSessionGroup(BaseModel):
    session_id: str
    conversations: List[ConversationItem]
    first_message_time: Optional[str] = None
    total: int


class ConversationSessionSummary(BaseModel):
    session_id: str
    first_message_time: Optional[str] = None
    last_message_time: Optional[str] = None
    message_count: int
    preview: Optional[str] = None


class ConversationsBySessionResponse(BaseModel):
    session_id: str
    mode: str
    conversations: List[ConversationItem]
    total: int


class ConversationsGroupedResponse(BaseModel):
    mode: str
    sessions: List[ConversationSessionGroup]
    total_conversations: int
    total_sessions: int


class DeleteConversationRequest(BaseModel):
    session_ids: List[str]


class DeleteConversationResponse(BaseModel):
    ok: bool
    deleted_count: int
    deleted_logs: int


class ExportConversationsResponse(BaseModel):
    exported_at: str
    mode: str
    sessions: List[ConversationSessionGroup]
    total_conversations: int
    total_sessions: int


class GeneralConversationsBySessionResponse(BaseModel):
    session_id: str
    store_name: str
    mode: str
    conversations: List[ConversationItem]
    total: int


class GeneralConversationsResponse(BaseModel):
    store_name: str
    mode: str
    sessions: List[ConversationSessionSummary]
    total_conversations: int
    total_sessions: int


class ExportGeneralConversationsResponse(BaseModel):
    exported_at: str
    store_name: str
    mode: str
    sessions: List[ConversationSessionGroup]
    total_conversations: int
    total_sessions: int
