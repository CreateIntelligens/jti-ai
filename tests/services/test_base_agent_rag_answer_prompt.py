from types import SimpleNamespace

import pytest

from app.models.session import Session
from app.services.base_agent import BaseAgent


def _text_response(text: str):
    part = SimpleNamespace(text=text)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(text=text, candidates=[candidate])


def _function_call_response(query: str):
    function_call = SimpleNamespace(
        name="search_knowledge",
        args={"queries": [query]},
    )
    part = SimpleNamespace(function_call=function_call)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(text="", candidates=[candidate])


class FakeSessionManager:
    def __init__(self, session: Session):
        self.session = session
        self.updated = []

    def get_session(self, session_id: str):
        return self.session if session_id == self.session.session_id else None

    def update_session(self, session: Session):
        self.updated.append(session)


class FakeChatSession:
    def __init__(self):
        self.sent_messages = []
        self._curated_history = []

    def send_message(self, message, config=None):
        self.sent_messages.append((message, config))
        if len(self.sent_messages) == 1:
            self._curated_history.append(SimpleNamespace(role="user", parts=[]))
            self._curated_history.append(SimpleNamespace(role="model", parts=[]))
            return _function_call_response("PRP是什麼?")

        self._curated_history.append(SimpleNamespace(role="user", parts=[]))
        self._curated_history.append(SimpleNamespace(role="model", parts=[]))
        return _text_response("PRP 是使用自體血液取得血小板濃縮液的治療。")


class FakeAgent(BaseAgent):
    def __init__(self, session_manager: FakeSessionManager, chat_session: FakeChatSession):
        super().__init__(model_name="test-model")
        self._fake_session_manager = session_manager
        self._fake_chat_session = chat_session

    @property
    def _session_manager(self):
        return self._fake_session_manager

    @property
    def _persona_map_attr(self) -> str:
        return "_unused"

    @property
    def _active_prompt_id_attr(self) -> str:
        return "_unused"

    @staticmethod
    def _get_store_name_for_language(language: str) -> str:
        return "__test__"

    @property
    def _rag_source_type(self) -> str:
        return "test_knowledge"

    def _get_default_persona(self, language: str) -> str:
        return "請根據知識庫回答。"

    def _build_system_instruction(self, persona, language, response_rule_sections, max_response_chars):
        return persona

    def _load_runtime_settings(self, prompt_manager, prompt_id, store_name):
        return self._load_default_runtime_settings()

    def _load_default_runtime_settings(self):
        sections = {"zh": {"role_scope": "", "scope_limits": "", "response_style": "", "knowledge_rules": ""}}
        return SimpleNamespace(response_rule_sections=sections, max_response_chars=600)

    def _get_session_state(self, session: Session) -> str:
        return "<state>"

    def _get_chat_fallback_message(self, language: str) -> str:
        return "抱歉，發生錯誤，請稍後再試。"

    def _get_or_create_chat_session(self, session: Session, model=None):
        return self._fake_chat_session

    async def _send_enriched_with_model_fallback(self, chat_session, enriched, force_config, session):
        return chat_session, chat_session.send_message(enriched, config=force_config)

    async def _execute_rag_tool(self, ai_query: str, user_message: str, session: Session):
        return "PRP 是 Platelet-Rich Plasma，中文常稱高濃度血小板血漿。", [
            {
                "title": "PRP.csv",
                "uri": "file:///PRP.csv",
                "text": "PRP 是 Platelet-Rich Plasma，中文常稱高濃度血小板血漿。",
            }
        ]

    def _sync_history_to_db_background(self, *args, **kwargs):
        return None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_chat_answers_from_rag_results_without_empty_response_recovery(monkeypatch):
    import app.services.gemini_service as gemini_service

    monkeypatch.setattr(gemini_service, "client", object())

    session = Session(session_id="sid-rag-answer", language="zh")
    session.metadata = {"store_name": "__hciot__", "model": "test-model"}
    chat_session = FakeChatSession()
    agent = FakeAgent(FakeSessionManager(session), chat_session)

    result = await agent.chat("sid-rag-answer", "PRP是啥?")

    assert result["message"] == "PRP 是使用自體血液取得血小板濃縮液的治療。"
    assert len(chat_session.sent_messages) == 2
    answer_prompt, answer_config = chat_session.sent_messages[1]
    assert "<知識庫查詢結果>" in answer_prompt
    assert "Platelet-Rich Plasma" in answer_prompt
    assert "PRP是啥?" in answer_prompt
    assert answer_config.tools is None
    assert result["citations"] == [
        {
            "title": "PRP.csv",
            "uri": "file:///PRP.csv",
            "text": "PRP 是 Platelet-Rich Plasma，中文常稱高濃度血小板血漿。",
        }
    ]
