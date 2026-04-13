"""
HCIoT main agent - patient education chat flow.
"""

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.gemini_service import gemini_with_retry, run_sync
from app.services.agent_utils import (
    extract_response_text,
    normalize_language,
    strip_citations,
)
from app.services.base_agent import FILE_SEARCH_MODEL, BaseAgent
from app.services.hciot.agent_prompts import (
    PERSONA,
    SESSION_STATE_TEMPLATES,
    build_intent_prompt,
    build_system_instruction,
)
from app.services.hciot.runtime_settings import (
    HCIOT_STORE_NAME,
    load_runtime_settings_from_prompt_manager,
)
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.session.session_manager_factory import get_hciot_session_manager

session_manager = get_hciot_session_manager()
logger = logging.getLogger(__name__)


class HciotMainAgent(BaseAgent):
    IMAGE_TOKEN_PATTERN = re.compile(r"IMG_[A-Za-z0-9_]+", re.IGNORECASE)

    def __init__(self):
        super().__init__(model_name=FILE_SEARCH_MODEL)

    @property
    def _session_manager(self):
        return session_manager

    @property
    def _persona_map_attr(self) -> str:
        return "hciot_persona_by_prompt"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__hciot__en" if normalize_language(language) == "en" else HCIOT_STORE_NAME

    @staticmethod
    def _get_file_search_store_name(language: str) -> str | None:
        lang_upper = normalize_language(language).upper()
        store_id = os.getenv(f"HCIOT_STORE_ID_{lang_upper}") or os.getenv("HCIOT_STORE_ID")
        if not store_id:
            return None
        if store_id.startswith("fileSearchStores/"):
            return store_id
        return f"fileSearchStores/{store_id}"

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
        template = SESSION_STATE_TEMPLATES.get(session.language, SESSION_STATE_TEMPLATES["zh"])
        return template.format(step_value=session.step.value)

    def _build_intent_prompt(self, query: str, language: str) -> str:
        return build_intent_prompt(query)

    def _intent_default_on_error(self) -> str:
        """HCIoT defaults to NO on intent check failure (block unrelated queries)."""
        return "NO"

    def _extract_file_search_citations(self, response) -> list[dict] | None:
        """Extract citation list for HCIoT, keeping chunk text for image-id matching."""
        return self._extract_citations(response, include_text=True)

    @classmethod
    def _extract_top_citation_image_id(
        cls,
        citations: list[dict] | None,
    ) -> str | None:
        """Return image_id from the top citation.

        1. Dedicated ``_IMG_`` CSV → read the row's raw ``img`` value
        2. IMG_ token in citation title
        3. IMG_ token in citation chunk text
        """
        if not isinstance(citations, list) or not citations:
            return None
        first = citations[0]
        if not isinstance(first, dict):
            return None

        title = first.get("title") or ""
        text = first.get("text") or ""
        filenames = [
            cls._citation_filename(title),
            cls._citation_filename(first.get("uri")),
        ]
        if any(filename and "_img_" in filename.lower() for filename in filenames):
            return cls._extract_image_id_from_dedicated_img_csv(filenames)

        for value in (title, text):
            match = cls.IMAGE_TOKEN_PATTERN.search(value)
            if match:
                return match.group(0)
        return None

    @classmethod
    def _extract_image_id_from_dedicated_img_csv(cls, filenames: list[str]) -> str | None:
        for filename in filenames:
            image_id = cls._extract_image_id_from_csv(filename, require_single_meaningful_row=True)
            if image_id:
                return image_id
        return None

    @classmethod
    def _clean_image_id(cls, raw: str) -> str | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        if "=" in raw:
            raw = raw.split("=", 1)[0].strip()
        if "/" in raw:
            raw = raw.split("/")[-1]
        if "." in raw:
            raw = raw.rsplit(".", 1)[0]
        return raw or None

    @classmethod
    def _extract_image_id_from_csv(
        cls,
        filename: str,
        *,
        require_single_meaningful_row: bool = False,
    ) -> str | None:
        """Read a CSV from knowledge store and return the row img value as image_id."""
        if not filename:
            return None
        try:
            import csv
            import io
            store = get_hciot_knowledge_store()
            doc = store.get_file("zh", filename) or store.get_file("en", filename)
            if not doc or not doc.get("data"):
                return None
            text = doc["data"].decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or "img" not in reader.fieldnames:
                return None
            rows = list(reader)
            if require_single_meaningful_row:
                meaningful_rows = [
                    row for row in rows
                    if any((row.get(key) or "").strip() for key in ("q", "a", "img"))
                ]
                if len(meaningful_rows) != 1:
                    return None
                return cls._clean_image_id(meaningful_rows[0].get("img") or "")

            for row in rows:
                image_id = cls._clean_image_id(row.get("img") or "")
                if image_id:
                    return image_id
        except Exception as e:
            logger.debug("Failed to extract image_id from CSV %s: %s", filename, e)
        return None

    @staticmethod
    def _citation_filename(value: str | None) -> str:
        if not isinstance(value, str) or not value.strip():
            return ""
        parsed = urlparse(value)
        candidate = parsed.path or value
        return os.path.basename(candidate).strip()

    @classmethod
    def _localize_citations(cls, language: str, citations: list[dict] | None) -> list[dict] | None:
        if not citations:
            return citations

        file_map = {
            item["name"].lower(): item.get("display_name") or item["name"]
            for item in get_hciot_knowledge_store().list_files(language)
            if item.get("name")
        }

        localized: list[dict] = []
        for citation in citations:
            if not isinstance(citation, dict):
                continue

            localized_citation = dict(citation)
            filename_candidates = [
                cls._citation_filename(localized_citation.get("title")),
                cls._citation_filename(localized_citation.get("uri")),
            ]
            for filename in filename_candidates:
                display_name = file_map.get(filename.lower())
                if display_name:
                    localized_citation["title"] = display_name
                    break
            localized.append(localized_citation)

        return localized or None

    async def chat(self, session_id: str, user_message: str) -> dict[str, Any]:
        try:
            if not _gemini_service.client:
                return {"error": "Gemini client not initialized", "message": "系統未正確初始化，請檢查 API Key 設定。"}

            session = session_manager.get_session(session_id)
            if session is None:
                return {"error": "Session not found", "message": "找不到對話記錄，請重新開始。"}

            kb_result, citations = await self._concurrent_intent_and_search(user_message, session.language, session_id)
            citations = self._localize_citations(session.language, citations)
            image_id = self._extract_top_citation_image_id(citations)

            session_state = self._get_session_state(session)
            enriched_message = self._build_enriched_message(session_state, user_message, session.language, kb_result)
            chat_session = self._get_or_create_chat_session(session)
            response = await run_sync(gemini_with_retry, lambda: chat_session.send_message(enriched_message))

            if enriched_message != user_message:
                self._clean_enriched_history(chat_session, user_message)

            final_message = extract_response_text(response)
            if not final_message:
                final_message = "目前無法回應，請稍後再試。"

            final_message = strip_citations(final_message)
            if not final_message:
                final_message = "目前無法回應，請稍後再試。"
            self._sync_history_to_db_background(session_id, user_message, final_message, citations)
            updated_session = session_manager.get_session(session_id)

            return {
                "message": final_message,
                "session": updated_session.model_dump() if updated_session else None,
                "tool_calls": [],
                "citations": citations,
                "image_id": image_id,
            }
        except Exception as e:
            logger.error(f"HCIoT chat failed: {e}", exc_info=True)
            return {"error": str(e), "message": f"抱歉，發生錯誤：{str(e)}"}


main_agent = HciotMainAgent()
