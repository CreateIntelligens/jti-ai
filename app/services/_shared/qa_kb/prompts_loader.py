"""Generic active persona / role-scope loader for QA extraction."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _active_prompt_language_value(prompt_map: object, active_id: str, language: str) -> str | None:
    if not isinstance(prompt_map, dict):
        return None

    raw_prompt = prompt_map.get(active_id)
    if not isinstance(raw_prompt, dict):
        return None

    nested_persona = raw_prompt.get("persona")
    language_values = nested_persona if isinstance(nested_persona, dict) else raw_prompt
    value = language_values.get(language)
    return value if isinstance(value, str) and value.strip() else None


def _active_role_scope(runtime_map: object, active_id: str, language: str) -> str | None:
    if not isinstance(runtime_map, dict):
        return None

    settings = runtime_map.get(active_id)
    if not isinstance(settings, dict):
        return None

    sections = settings.get("response_rule_sections")
    if not isinstance(sections, dict):
        return None

    language_sections = sections.get(language)
    if not isinstance(language_sections, dict):
        return None

    value = language_sections.get("role_scope")
    return value if isinstance(value, str) and value.strip() else None


def _default_prompt_manager() -> Any:
    from app import deps

    return deps.prompt_manager


def load_active_persona_and_role_scope(
    *,
    language: str,
    store_name_for_language: Callable[[str], str],
    active_id_attr: str,
    persona_map_attr: str,
    runtime_map_attr: str,
    fallback_persona: str,
    fallback_role_scope: str,
    prompt_manager: Any | None = None,
    log_label: str = "QA prompts",
) -> tuple[str, str]:
    """Return active persona/scope from PromptManager, falling back safely."""
    persona = fallback_persona
    role_scope = fallback_role_scope

    try:
        pm = prompt_manager if prompt_manager is not None else _default_prompt_manager()
        if not pm:
            return persona, role_scope

        store_prompts = pm.get_store_prompts(store_name_for_language(language))
        active_id = getattr(store_prompts, active_id_attr, None)
        if not active_id:
            return persona, role_scope

        active_persona = _active_prompt_language_value(
            getattr(store_prompts, persona_map_attr, None),
            active_id,
            language,
        )
        if active_persona is not None:
            persona = active_persona

        active_scope = _active_role_scope(
            getattr(store_prompts, runtime_map_attr, None),
            active_id,
            language,
        )
        if active_scope is not None:
            role_scope = active_scope
    except Exception as e:
        logger.warning("[%s] Failed to load active prompt context, using fallback: %s", log_label, e)

    return persona, role_scope
