"""Regression tests for migrating JTI onto General shared runtimes."""

from __future__ import annotations

import importlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_quiz_runtime_lives_in_general_package() -> None:
    runtime = importlib.import_module("app.services.general.quiz_runtime")
    helpers = importlib.import_module("app.services.general.quiz_helpers")

    assert callable(runtime.execute_quiz_start)
    assert callable(runtime.handle_quiz_message)
    assert callable(helpers.is_quiz_start_intent)


def test_production_code_does_not_import_legacy_jti_quiz_runtime() -> None:
    legacy_imports = (
        "app.services.jti.runtime_quiz_flow",
        "app.services.jti.quiz_helpers",
    )
    offenders: list[str] = []

    for path in (PROJECT_ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(legacy in source for legacy in legacy_imports):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_jti_agent_uses_general_managed_agent_runtime() -> None:
    from app.services.general.managed_agent import ManagedAppAgent
    from app.services.jti.main_agent import MainAgent, main_agent

    assert issubclass(MainAgent, ManagedAppAgent)
    assert isinstance(main_agent, ManagedAppAgent)
    assert main_agent.config.app == "jti"
    assert main_agent._get_store_name_for_language("zh") == "__jti__"
    assert main_agent._get_store_name_for_language("en") == "__jti__en"
    assert main_agent._rag_source_type == "jti_knowledge"


def test_jti_chat_and_quiz_routes_delegate_to_general_services() -> None:
    from app.routers.jti import chat, quiz
    from app.services.general.managed_chat import ManagedChatService
    from app.services.general.managed_quiz import ManagedQuizService

    assert isinstance(chat.chat_service, ManagedChatService)
    assert isinstance(quiz.quiz_service, ManagedQuizService)


def test_jti_chat_and_quiz_route_contract_is_unchanged() -> None:
    from app.routers.jti import chat, quiz

    routers = (
        chat.runtime_router,
        chat.compat_history_router,
        chat.admin_history_router,
        chat.compat_history_admin_router,
        chat.admin_history_admin_router,
        quiz.router,
    )
    actual = {
        (method, route.path)
        for router in routers
        for route in router.routes
        for method in (route.methods or set())
    }

    assert actual == {
        ("GET", "/api/jti/tts/{tts_message_id}"),
        ("POST", "/api/jti/tts"),
        ("POST", "/api/jti/chat/start"),
        ("POST", "/api/jti/chat/message"),
        ("GET", "/api/jti/history"),
        ("GET", "/api/jti/history/export"),
        ("GET", "/api/jti-admin/conversations"),
        ("GET", "/api/jti-admin/conversations/export"),
        ("DELETE", "/api/jti/history"),
        ("DELETE", "/api/jti-admin/conversations"),
        ("POST", "/quiz/start"),
        ("POST", "/quiz/pause"),
    }


def test_jti_quiz_bank_is_fixed_store_adapter_over_general_handlers() -> None:
    from app.routers.jti import quiz_bank

    assert quiz_bank.JTI_STORE_NAME == "__jti__"
    assert quiz_bank.general_quiz_bank.router.prefix.startswith(
        "/api/general/quiz-bank/"
    )


def test_jti_quiz_bank_route_contract_is_unchanged() -> None:
    from app.routers.jti.quiz_bank import router

    actual = {
        (method, route.path)
        for route in router.routes
        for method in (route.methods or set())
    }
    assert actual == {
        ("GET", "/banks/"),
        ("POST", "/banks/"),
        ("GET", "/banks/{bank_id}"),
        ("PATCH", "/banks/{bank_id}"),
        ("DELETE", "/banks/{bank_id}"),
        ("POST", "/banks/{bank_id}/activate"),
        ("GET", "/questions/"),
        ("GET", "/questions/{question_id}"),
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


def test_jti_prompts_remain_shared_factory_adapter() -> None:
    from app.routers._shared.persona_router import PersonaRouterConfig
    from app.routers.jti import prompts

    assert isinstance(prompts._config, PersonaRouterConfig)
    assert prompts._config.store_name_zh == "__jti__"
    assert prompts._config.store_name_en == "__jti__en"

    actual = {
        (method, route.path)
        for route in prompts.router.routes
        for method in (route.methods or set())
    }
    assert actual == {
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
