"""Contracts for ESG's dedicated managed-app services and routers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.session import Session
from app.prompts import StorePrompts
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.general.managed_chat import ManagedChatConfig, ManagedChatService
from app.services.quiz.config import QuizFlowConfig


ESG_QUIZ_COPY = {
    "opening": {
        "zh": "來測測你對三立永續的了解吧！請選出正確答案：",
        "en": "Test your knowledge of SET's sustainability journey! Pick the correct answer:",
    },
    "already_done": {
        "zh": "你已經作答過囉！想再玩一次請重新整理頁面開始新的對話。",
        "en": "You've already answered! Refresh the page to start a new session.",
    },
}


def _route_contract(router) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in router.routes
        for method in (route.methods or set())
    }


def _mounted_paths(app) -> set[str]:
    paths: set[str] = set()

    def collect(routes, prefix: str = "") -> None:
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                paths.add(f"{prefix}{path}")
                continue

            original_router = getattr(route, "original_router", None)
            include_context = getattr(route, "include_context", None)
            if original_router is not None and include_context is not None:
                collect(
                    original_router.routes,
                    f"{prefix}{include_context.prefix}",
                )

    collect(app.routes)
    return paths


def test_shared_models_define_dedicated_esg_configuration() -> None:
    from app.services import db_names
    from app.services.quiz import config

    assert config.ESG_STORE_NAME == "__esg__"
    assert db_names.ESG_DB_NAME == "esg_app"

    fields = StorePrompts.model_fields
    assert {
        "esg_prompt_index",
        "esg_active_prompt_id",
        "esg_runtime_settings_by_prompt",
        "esg_persona_by_prompt",
    } <= fields.keys()


def test_esg_manager_factories_are_dedicated(monkeypatch) -> None:
    from app.services.session import session_manager_factory as factory

    monkeypatch.delenv("MONGODB_URI", raising=False)
    factory._singletons.clear()
    try:
        esg_session_manager = factory.get_esg_session_manager()
        esg_logger = factory.get_esg_conversation_logger()

        assert esg_session_manager is not factory.get_general_chat_session_manager()
        assert esg_logger is not factory.get_general_conversation_logger()
        assert factory._singletons["esg_session_manager"] is esg_session_manager
        assert factory._singletons["esg_conversation_logger"] is esg_logger
    finally:
        factory._singletons.clear()


def test_managed_chat_supports_no_tts_and_configured_quiz_keywords() -> None:
    session = Session(session_id="esg-session", language="zh")
    session_manager = MagicMock()
    session_manager.get_session.return_value = session
    conversation_logger = MagicMock()
    agent = MagicMock()
    agent.chat = AsyncMock(return_value={"message": "一般回答"})

    quiz_config = QuizFlowConfig(
        session_manager_getter=lambda: session_manager,
        conversation_logger_getter=lambda: conversation_logger,
        agent=agent,
        store_name="__esg__",
        mode="esg",
        keywords=["問答"],
        negative_keywords=[],
        tts_fn=lambda _text, _language: None,
    )
    service = ManagedChatService(
        ManagedChatConfig(
            app="esg",
            opening_messages={"zh": "歡迎"},
            session_manager_getter=lambda: session_manager,
            conversation_logger_getter=lambda: conversation_logger,
            agent=agent,
            quiz=quiz_config,
        )
    )

    quiz_response = ChatResponse(message="開始 ESG 問答")
    with patch(
        "app.services.general.managed_chat.execute_quiz_start",
        new=AsyncMock(return_value=quiz_response),
    ) as execute_quiz_start:
        response = asyncio.run(
            service.send_message(
                ChatRequest(session_id=session.session_id, message="開始問答")
            )
        )

    assert response == quiz_response
    execute_quiz_start.assert_awaited_once()
    agent.chat.assert_not_awaited()


def test_esg_service_configuration_matches_baseline() -> None:
    from app.services.esg.main_agent import ESG_AGENT_CONFIG, EsgMainAgent, main_agent
    from app.services.esg.quiz_flow import ESG_QUIZ_CONFIG
    from app.services.general.managed_agent import ManagedAppAgent
    from app.services.quiz.config import ESG_STORE_NAME

    assert issubclass(EsgMainAgent, ManagedAppAgent)
    assert isinstance(main_agent, ManagedAppAgent)
    assert ESG_AGENT_CONFIG.app == "esg"
    assert main_agent._get_store_name_for_language("zh") == "__esg__"
    assert main_agent._get_store_name_for_language("en") == "__esg__en"
    assert main_agent._rag_source_type == "esg_knowledge"

    assert ESG_QUIZ_CONFIG.store_name == ESG_STORE_NAME
    assert ESG_QUIZ_CONFIG.mode == "esg"
    assert ESG_QUIZ_CONFIG.keywords == ["測驗", "quiz", "問答"]
    assert ESG_QUIZ_CONFIG.negative_keywords == []
    assert ESG_QUIZ_CONFIG.copy_templates == ESG_QUIZ_COPY
    assert ESG_QUIZ_CONFIG.tts_manager_getter is None
    assert ESG_QUIZ_CONFIG.tts_fn("文字", "zh") is None


def test_esg_prompt_router_uses_dedicated_storage() -> None:
    from app.routers.esg import prompts
    from app.routers._shared.persona_router import FlatPersonaAdapter

    assert prompts._config.store_name_zh == "__esg__"
    assert prompts._config.store_name_en == "__esg__en"
    assert prompts._config.prompt_index_attr == "esg_prompt_index"
    assert prompts._config.active_prompt_id_attr == "esg_active_prompt_id"
    assert isinstance(prompts._config.persona_adapter, FlatPersonaAdapter)
    assert prompts._config.persona_adapter.attr == "esg_persona_by_prompt"


def test_esg_router_contracts() -> None:
    from app.routers.esg import chat, prompts, quiz, quiz_bank

    chat_routes = (
        chat.runtime_router,
        chat.compat_history_router,
        chat.admin_history_router,
        chat.compat_history_admin_router,
        chat.admin_history_admin_router,
    )
    actual_chat = {
        contract
        for router in chat_routes
        for contract in _route_contract(router)
    }
    assert actual_chat == {
        ("POST", "/api/esg/chat/start"),
        ("POST", "/api/esg/chat/message"),
        ("POST", "/api/esg/tts"),
        ("GET", "/api/esg/tts/{tts_message_id}"),
        ("GET", "/api/esg/history"),
        ("GET", "/api/esg/history/export"),
        ("DELETE", "/api/esg/history"),
        ("GET", "/api/esg-admin/conversations"),
        ("GET", "/api/esg-admin/conversations/export"),
        ("DELETE", "/api/esg-admin/conversations"),
    }
    assert _route_contract(quiz.router) == {
        ("POST", "/quiz/start"),
        ("POST", "/quiz/pause"),
    }
    assert _route_contract(prompts.router) == {
        ("GET", "/"),
        ("POST", "/"),
        ("POST", "/clone"),
        ("PUT", "/{prompt_id}"),
        ("DELETE", "/{prompt_id}"),
        ("POST", "/active"),
        ("GET", "/active"),
        ("GET", "/runtime-settings"),
        ("POST", "/runtime-settings"),
    }
    assert quiz_bank.ESG_STORE_NAME == "__esg__"
    assert _route_contract(quiz_bank.router) == {
        ("GET", "/banks/"),
        ("POST", "/banks/"),
        ("DELETE", "/banks/{bank_id}"),
        ("POST", "/banks/{bank_id}/activate"),
        ("GET", "/questions/"),
        ("POST", "/questions/"),
        ("PUT", "/questions/{question_id}"),
        ("DELETE", "/questions/{question_id}"),
        ("GET", "/quiz-results/sets/"),
        ("POST", "/quiz-results/sets/"),
        ("DELETE", "/quiz-results/sets/{set_id}"),
        ("POST", "/quiz-results/sets/{set_id}/activate"),
        ("GET", "/quiz-results/"),
        ("PUT", "/quiz-results/{quiz_id}"),
        ("GET", "/stats/"),
        ("POST", "/transfer/import"),
        ("GET", "/transfer/export"),
    }


def test_main_mounts_esg_routes_and_preserves_general_routes() -> None:
    from tests.support.app_test_support import get_test_app

    app = get_test_app()
    paths = _mounted_paths(app)

    assert {
        "/api/esg/chat/start",
        "/api/esg/chat/message",
        "/api/esg/quiz/start",
        "/api/esg/quiz/pause",
        "/api/esg-admin/prompts/",
        "/api/esg/prompts/",
        "/api/esg-admin/quiz-bank/banks/",
        "/api/esg/quiz-bank/banks/",
    } <= paths
    assert "/api/chat/start" in paths
    assert "/api/general/quiz-bank/{store_name}/banks/" in paths
