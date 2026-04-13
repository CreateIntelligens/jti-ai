"""HCIoT runtime settings per prompt: rule sections, welcome text, and length limit."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.services.hciot.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    DEFAULT_RESPONSE_RULE_SECTIONS,
    WELCOME_TEXT,
)

HCIOT_STORE_NAME = "__hciot__"
SYSTEM_DEFAULT_PROMPT_ID = "system_default"
_TTS_CHARACTER_ENV = "HCIOT_TTS_CHARACTER"
_TTS_CHARACTER_FALLBACK = "healthy2"


def _parse_tts_characters(raw: Optional[str]) -> list[str]:
    source = raw or _TTS_CHARACTER_FALLBACK
    characters = [character.strip() for character in source.split(",") if character.strip()]
    return characters or [_TTS_CHARACTER_FALLBACK]


def get_available_tts_characters() -> list[str]:
    return _parse_tts_characters(os.getenv(_TTS_CHARACTER_ENV, _TTS_CHARACTER_FALLBACK))


class RuleSections(BaseModel):
    role_scope: str
    scope_limits: str
    response_style: str
    knowledge_rules: str


class WelcomeBlock(BaseModel):
    title: str
    description: str


class HciotRuntimeSettings(BaseModel):
    response_rule_sections: Dict[str, RuleSections] = Field(
        default_factory=lambda: {
            "zh": RuleSections(**DEFAULT_RESPONSE_RULE_SECTIONS["zh"]),
            "en": RuleSections(**DEFAULT_RESPONSE_RULE_SECTIONS["en"]),
        }
    )
    welcome: Dict[str, WelcomeBlock] = Field(
        default_factory=lambda: {
            "zh": WelcomeBlock(**WELCOME_TEXT["zh"]),
            "en": WelcomeBlock(**WELCOME_TEXT["en"]),
        }
    )
    max_response_chars: int = Field(default=DEFAULT_MAX_RESPONSE_CHARS, ge=30, le=100)


RULE_SECTION_FIELDS = ("role_scope", "scope_limits", "response_style", "knowledge_rules")


def get_default_runtime_settings() -> HciotRuntimeSettings:
    return HciotRuntimeSettings()


def _resolve_runtime_prompt_id(store_prompts, prompt_id: Optional[str]) -> str:
    if isinstance(prompt_id, str) and prompt_id.strip():
        return prompt_id
    active_prompt_id = getattr(store_prompts, "active_prompt_id", None)
    return active_prompt_id or SYSTEM_DEFAULT_PROMPT_ID


def _load_raw_runtime_settings(store_prompts, prompt_id: str) -> Optional[Dict[str, Any]]:
    raw_by_prompt = getattr(store_prompts, "hciot_runtime_settings_by_prompt", None)
    if isinstance(raw_by_prompt, dict):
        raw_for_prompt = raw_by_prompt.get(prompt_id)
        if isinstance(raw_for_prompt, dict):
            return raw_for_prompt

        raw_for_default = raw_by_prompt.get(SYSTEM_DEFAULT_PROMPT_ID)
        if isinstance(raw_for_default, dict):
            return raw_for_default

    return None


def _normalize_runtime_settings(raw: Optional[Dict[str, Any]]) -> HciotRuntimeSettings:
    settings = get_default_runtime_settings().model_dump()

    if not isinstance(raw, dict):
        return HciotRuntimeSettings(**settings)

    raw_sections = raw.get("response_rule_sections")
    if isinstance(raw_sections, dict):
        for lang in ("zh", "en"):
            section_data = raw_sections.get(lang)
            if isinstance(section_data, dict):
                for field in RULE_SECTION_FIELDS:
                    value = section_data.get(field)
                    if isinstance(value, str) and value.strip():
                        settings["response_rule_sections"][lang][field] = value

    raw_welcome = raw.get("welcome")
    if isinstance(raw_welcome, dict):
        for lang in ("zh", "en"):
            block = raw_welcome.get(lang)
            if isinstance(block, dict):
                title = block.get("title")
                description = block.get("description")
                if isinstance(title, str) and title.strip():
                    settings["welcome"][lang]["title"] = title
                if isinstance(description, str) and description.strip():
                    settings["welcome"][lang]["description"] = description

    raw_limit = raw.get("max_response_chars")
    if isinstance(raw_limit, int):
        settings["max_response_chars"] = raw_limit

    return HciotRuntimeSettings(**settings)


def load_runtime_settings_from_prompt_manager(
    prompt_manager,
    prompt_id: Optional[str] = None,
    store_name: str = HCIOT_STORE_NAME,
) -> HciotRuntimeSettings:
    if not prompt_manager:
        return get_default_runtime_settings()

    store_prompts = prompt_manager._load_store_prompts(store_name)
    runtime_prompt_id = _resolve_runtime_prompt_id(store_prompts, prompt_id)
    raw = _load_raw_runtime_settings(store_prompts, runtime_prompt_id)

    try:
        settings = _normalize_runtime_settings(raw)
        if runtime_prompt_id == SYSTEM_DEFAULT_PROMPT_ID:
            settings.max_response_chars = DEFAULT_MAX_RESPONSE_CHARS
        return settings
    except Exception:
        return get_default_runtime_settings()


def save_runtime_settings_to_prompt_manager(
    prompt_manager,
    settings: HciotRuntimeSettings,
    prompt_id: Optional[str] = None,
    store_name: str = HCIOT_STORE_NAME,
) -> str:
    store_prompts = prompt_manager._load_store_prompts(store_name)
    runtime_prompt_id = _resolve_runtime_prompt_id(store_prompts, prompt_id)

    runtime_map = getattr(store_prompts, "hciot_runtime_settings_by_prompt", None)
    if not isinstance(runtime_map, dict):
        runtime_map = {}
    runtime_map[runtime_prompt_id] = settings.model_dump()
    store_prompts.hciot_runtime_settings_by_prompt = runtime_map
    prompt_manager._save_store_prompts(store_prompts)
    return runtime_prompt_id
