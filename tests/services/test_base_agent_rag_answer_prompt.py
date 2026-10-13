from types import SimpleNamespace

import pytest

from app import models_config
from app.models.session import Session
from app.services import base_agent as base_agent_module
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


class ResultChatSession:
    def __init__(self, result):
        self.result = result
        self.sent_configs = []

    def send_message(self, _message, config=None):
        self.sent_configs.append(config)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _configure_model_fallback(monkeypatch, model_chain):
    monkeypatch.setattr(
        models_config,
        "fallback_chain",
        lambda _model, _client: model_chain,
    )
    monkeypatch.setattr(
        base_agent_module,
        "get_client_by_index",
        lambda _index: object(),
    )
    monkeypatch.setattr(
        base_agent_module,
        "resolve_key_index_for_store",
        lambda _store: 0,
    )


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

    async def _execute_rag_tool(self, ai_query: str, user_message: str, session: Session, query_vectors=None):
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
async def test_model_fallback_rebuilds_thinking_config(monkeypatch):
    session = Session(metadata={"model": "gemini-2.5-flash-lite"})
    session_manager = FakeSessionManager(session)
    fallback_response = _text_response("OK")
    fallback_chat = ResultChatSession(fallback_response)
    initial_chat = ResultChatSession(RuntimeError("404 model not found"))
    agent = FakeAgent(session_manager, fallback_chat)

    _configure_model_fallback(
        monkeypatch,
        (
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash-lite",
        ),
    )
    initial_config = agent._get_force_tool_config(session)

    _, response = await BaseAgent._send_enriched_with_model_fallback(
        agent,
        initial_chat,
        "question",
        initial_config,
        session,
    )

    assert response is fallback_response
    assert session.metadata["model"] == "gemini-3.5-flash-lite"
    assert initial_config.thinking_config.thinking_budget == 0
    assert fallback_chat.sent_configs[0].thinking_config is None


@pytest.mark.anyio
async def test_invalid_argument_does_not_trigger_model_fallback(monkeypatch):
    session = Session(metadata={"model": "gemini-flash-lite-latest"})
    session_manager = FakeSessionManager(session)
    initial_chat = ResultChatSession(RuntimeError("400 INVALID_ARGUMENT"))
    agent = FakeAgent(session_manager, ResultChatSession(_text_response("unused")))

    _configure_model_fallback(
        monkeypatch,
        (
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
        ),
    )
    initial_config = agent._get_force_tool_config(session)

    assert initial_config.thinking_config is None

    with pytest.raises(RuntimeError, match="400 INVALID_ARGUMENT"):
        await BaseAgent._send_enriched_with_model_fallback(
            agent,
            initial_chat,
            "question",
            initial_config,
            session,
        )

    assert session.metadata["model"] == "gemini-flash-lite-latest"
    assert session_manager.updated == []


@pytest.mark.anyio
async def test_invalid_key_rebuilds_session_on_another_key(monkeypatch):
    """key 被刪除時，這次請求就換 key 重送，使用者不會看到錯誤。"""
    session = Session(metadata={"model": "gemini-flash-lite-latest"})
    rebuilt = ResultChatSession(_text_response("OK"))
    agent = FakeAgent(FakeSessionManager(session), rebuilt)
    dead_client = object()
    marked = []
    monkeypatch.setattr(base_agent_module, "get_client_by_index", lambda _i: dead_client)
    monkeypatch.setattr(base_agent_module, "resolve_key_index_for_store", lambda _s: 2)
    monkeypatch.setattr(
        base_agent_module, "mark_client_invalid", lambda c: marked.append(c) or True
    )
    calls = []

    async def send(chat_session, enriched, force_config, session):
        calls.append(chat_session)
        if len(calls) == 1:
            raise RuntimeError("400 INVALID_ARGUMENT ... 'reason': 'API_KEY_INVALID'")
        return chat_session, chat_session.send_message(enriched, config=force_config)

    monkeypatch.setattr(agent, "_send_enriched_with_model_fallback", send)
    chat_session, response = await agent._send_with_key_failover(
        ResultChatSession(_text_response("unused")), "q", None, session
    )

    assert marked == [dead_client]
    assert chat_session is rebuilt
    assert response.text == "OK"


@pytest.mark.anyio
async def test_non_key_errors_do_not_switch_keys(monkeypatch):
    session = Session(metadata={"model": "gemini-flash-lite-latest"})
    agent = FakeAgent(FakeSessionManager(session), ResultChatSession(_text_response("x")))
    marked = []
    monkeypatch.setattr(base_agent_module, "mark_client_invalid", lambda c: marked.append(c))

    async def send(*_args):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(agent, "_send_enriched_with_model_fallback", send)
    with pytest.raises(RuntimeError, match="429"):
        await agent._send_with_key_failover(None, "q", None, session)
    assert marked == []


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


class _MissedCrisisChatSession(FakeChatSession):
    """模型漏判：對「我想從頂樓跳下去」只回 119，還寫成國字（10/13 開發機實測）。"""

    def send_message(self, message, config=None):
        response = super().send_message(message, config)
        if len(self.sent_messages) == 2:
            return _text_response("聽得到您說的話。請先撥打一一九或尋求專業人員協助。")
        return response


class _CrisisAgent(FakeAgent):
    def __init__(self, session_manager, chat_session):
        super().__init__(session_manager, chat_session)
        self.saved_history = []

    async def _execute_rag_tool(self, ai_query, user_message, session, query_vectors=None):
        return "嚴重扭傷怎麼辦？掌握PRICE原則", [
            {"title": "足踝扭傷.csv", "uri": "file:///a.csv", "text": "PRICE", "image_id": "足踝扭傷", "url": "https://x"}
        ]

    def _post_process_chat_result(self, session, final_text, citations, extra_meta):
        top = (citations or [{}])[0]
        return {"image_id": top.get("image_id"), "url": top.get("url")}

    def _sync_history_to_db_background(self, session_id, user_message, final_text, citations=None):
        self.saved_history.append(final_text)


@pytest.mark.anyio
async def test_chat_treats_explicit_self_harm_as_crisis_when_model_misses_it(monkeypatch):
    """VH-398：不靠模型自律，chat() 的最終輸出必須有專線、沒有任何圖片或連結，歷史存修正後文字。"""
    import app.services.gemini_service as gemini_service

    monkeypatch.setattr(gemini_service, "client", object())
    session = Session(session_id="sid-crisis", language="zh")
    session.metadata = {"store_name": "__hciot__", "model": "test-model"}
    agent = _CrisisAgent(FakeSessionManager(session), _MissedCrisisChatSession())

    result = await agent.chat("sid-crisis", "我想從頂樓跳下去")

    assert "安心專線1925" in result["message"] and "生命線1995" in result["message"]
    assert "119" in result["message"] and "一一九" not in result["message"]
    assert result["image_id"] is None and result["url"] is None
    assert all("image_id" not in c and "url" not in c for c in result["citations"])
    assert agent.saved_history == [result["message"]]
