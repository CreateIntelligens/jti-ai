"""
HCIoT main agent - patient education chat flow.

Uses Gemini function calling: the model decides when to search the
knowledge base via a `search_knowledge` tool, so the query naturally
includes conversational context.
"""

import logging
import os
from typing import Any

from google.genai import types
import app.deps as deps

from app.models.session import Session
from app.services.agent_utils import build_search_knowledge_decl, normalize_language
from app.services.base_agent import BaseAgent
from app.services.hciot.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_system_instruction,
)
from app.services.hciot.runtime_settings import (
    HCIOT_STORE_NAME,
    load_runtime_settings_from_prompt_manager,
)
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.hciot.tts import to_hciot_tts_text
logger = logging.getLogger(__name__)


def _get_session_manager():
    return deps.get_hciot_session_manager()

# ---------------------------------------------------------------------------
# RAG function declaration for Gemini function calling
# ---------------------------------------------------------------------------
_SEARCH_KNOWLEDGE_DECL = build_search_knowledge_decl(
    domain_description=(
        "搜尋醫院衛教知識庫，查詢疾病、治療、照護、檢查、藥物、手術、復健等相關資料。"
        "若使用者一次提出多個獨立主題的問題，請在同一次呼叫中將每個獨立問題各自填入 queries 陣列。"
    ),
    queries_description=(
        "使用者問題拆解後的獨立查詢列表，必須使用繁體中文，每一筆應為完整的問題描述（包含上下文）。"
        "若使用者只有一個問題，仍以單元素陣列回傳。即使使用者用英文提問，每筆 query 也必須翻譯成中文。"
    ),
)

_RAG_TOOL = types.Tool(function_declarations=[_SEARCH_KNOWLEDGE_DECL])


class HciotMainAgent(BaseAgent):
    CHAT_MODEL = "gemini-3.1-flash-lite-preview"

    def __init__(self):
        super().__init__(model_name=self.CHAT_MODEL)

    @property
    def _session_manager(self):
        return _get_session_manager()

    @property
    def _persona_map_attr(self) -> str:
        return "hciot_persona_by_prompt"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__hciot__en" if normalize_language(language) == "en" else HCIOT_STORE_NAME

    @property
    def _rag_source_type(self) -> str:
        return "hciot_knowledge"

    @property
    def _rag_search_language(self) -> str | None:
        return "zh"

    @property
    def _rag_tool_declaration(self) -> types.Tool | None:
        return _RAG_TOOL

    def _get_default_persona(self, language: str) -> str:
        return PERSONA.get(language, PERSONA["zh"])

    def _build_system_instruction(self, persona, language, response_rule_sections, max_response_chars):
        return build_system_instruction(
            persona=persona, language=language,
            response_rule_sections=response_rule_sections,
            limit=max_response_chars,
        )

    def _load_runtime_settings(self, prompt_manager, prompt_id, store_name):
        return load_runtime_settings_from_prompt_manager(prompt_manager, prompt_id, store_name=store_name)

    def _load_default_runtime_settings(self):
        return load_runtime_settings_from_prompt_manager(None)

    def _get_session_state(self, session: Session) -> str:
        from datetime import datetime, timezone
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        return template.format(step_value=session.step.value, now=now)

    @staticmethod
    def _extract_image_id(citations: list[dict] | None) -> str | None:
        """Return image_id only if the top-ranked citation carries one."""
        if not citations:
            return None
        return citations[0].get("image_id") or None

    @staticmethod
    def _extract_url(citations: list[dict] | None) -> str | None:
        """Return url only if the top-ranked citation carries one."""
        if not citations:
            return None
        return citations[0].get("url") or None

    @staticmethod
    def _localize_citations(language: str, citations: list[dict] | None) -> list[dict] | None:
        """Replace filenames with display names from the knowledge store."""
        if not citations:
            return citations

        store_files = get_hciot_knowledge_store().list_files(language)
        file_map = {f["name"].lower(): f.get("display_name") or f["name"] for f in store_files if f.get("name")}

        localized = []
        for c in citations:
            target = dict(c)
            for key in ("title", "uri"):
                raw = (target.get(key) or "").strip()
                name = os.path.basename(raw).lower()
                if name in file_map:
                    target["title"] = file_map[name]
                    break
            localized.append(target)
        return localized

    # ------------------------------------------------------------------
    # Function-calling chat loop
    # ------------------------------------------------------------------
    def _preprocess_chat_data(self, session: Session, citations: list[dict] | None) -> tuple[list[dict] | None, dict[str, Any]]:
        localized = self._localize_citations(session.language, citations)
        image_id = self._extract_image_id(localized)
        url = self._extract_url(localized)
        return localized, {"image_id": image_id, "url": url}

    def _post_process_chat_result(self, session: Session, response_text: str, citations: list[dict] | None, extra_meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "image_id": extra_meta.get("image_id"),
            "url": extra_meta.get("url"),
            "tts_text": to_hciot_tts_text(response_text, session.language),
        }

    def _get_chat_fallback_message(self, language: str) -> str:
        return "目前無法回應，請稍後再試。"


main_agent = HciotMainAgent()
