"""
Main Agent - 核心對話邏輯

架構：
- Gemini function calling: 模型決定何時查知識庫，query 帶對話上下文
- 雙路 RAG（AI 改寫 query + 原始 user message），merge & dedupe
- Quiz 流程由 router 層接管，不經過此 agent
"""

import logging
from typing import Any

from datetime import datetime, timezone
from google.genai import types
import app.deps as deps
from app.models.session import Session
from app.services.agent_utils import build_search_knowledge_decl, normalize_language
from app.services.base_agent import BaseAgent
from app.services.jti.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.jti.runtime_settings import (
    load_runtime_settings_from_prompt_manager,
)
from app.services.jti.tts import to_jti_tts_text

logger = logging.getLogger(__name__)


def _get_session_manager():
    return deps.get_jti_session_manager()

# ---------------------------------------------------------------------------
# RAG function declaration for Gemini function calling
# ---------------------------------------------------------------------------
_SEARCH_KNOWLEDGE_DECL = build_search_knowledge_decl(
    domain_description=(
        "搜尋知識庫，查詢產品資訊、規格、相關活動或其他常見問題。"
        "若使用者一次提出多個獨立主題的問題，請在同一次呼叫中將每個獨立問題各自填入 queries 陣列。"
    ),
    queries_description=(
        "使用者問題拆解後的獨立查詢列表，每一筆應為完整的問題描述（包含上下文）。"
        "若使用者只有一個問題，仍以單元素陣列回傳。"
    ),
)

_RAG_TOOL = types.Tool(function_declarations=[_SEARCH_KNOWLEDGE_DECL])


class MainAgent(BaseAgent):
    """主要對話 Agent"""

    # JTI 用固定的 flash-lite，避免較強的 model 自行進行測驗流程
    CHAT_MODEL = "gemini-3.1-flash-lite-preview"

    def __init__(self):
        super().__init__(model_name=self.CHAT_MODEL)

    @property
    def _session_manager(self):
        return _get_session_manager()

    @property
    def _persona_map_attr(self) -> str:
        return "jti_profiles_by_prompt"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__jti__en" if normalize_language(language) == "en" else "__jti__"

    @property
    def _rag_source_type(self) -> str:
        return "jti_knowledge"

    @property
    def _rag_tool_declaration(self) -> types.Tool | None:
        return _RAG_TOOL

    def _get_default_persona(self, language: str) -> str:
        return PERSONA.get(language, PERSONA["zh"])

    def _build_system_instruction(self, persona, language, response_rule_sections, max_response_chars):
        return build_system_instruction(
            persona=persona, language=language,
            response_rule_sections=response_rule_sections,
            max_response_chars=max_response_chars,
        )

    def _load_runtime_settings(self, prompt_manager, prompt_id, store_name):
        return load_runtime_settings_from_prompt_manager(prompt_manager, prompt_id, store_name=store_name)

    def _load_default_runtime_settings(self):
        return load_runtime_settings_from_prompt_manager(None)

    def _get_session_state(self, session: Session) -> str:
        """取得動態 Session 狀態（會變化的資訊）"""
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        not_yet = "Not calculated yet" if session.language == "en" else "尚未計算"
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        return template.format(
            step_value=session.step.value,
            answers_count=len(session.answers),
            quiz_result=session.quiz_result_id or not_yet,
            now=now,
        )

    def _get_question_label(self, language: str) -> str:
        return "User question:" if language == "en" else "使用者問題："

    def _post_process_chat_result(self, session: Session, response_text: str, citations: list[dict] | None, extra_meta: dict[str, Any]) -> dict[str, Any]:
        return {"tts_text": to_jti_tts_text(response_text, session.language)}

    def _get_chat_fallback_message(self, language: str) -> str:
        return "AI目前故障 請聯絡"


# 全域實例
main_agent = MainAgent()
