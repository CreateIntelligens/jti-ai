"""HCIoT runtime settings per prompt: rule sections, welcome text, and length limit."""

from __future__ import annotations

import os
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.services._shared.runtime_settings_base import (
    FlatRuntimeSettingsAdapter,
    RULE_SECTION_FIELDS,
    SYSTEM_DEFAULT_PROMPT_ID,
    RuleSections,
    RuntimeSettingsRepo,
    WelcomeBlock,
)
from app.services.hciot.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    DEFAULT_RESPONSE_RULE_SECTIONS,
    WELCOME_TEXT,
)

HCIOT_STORE_NAME = "__hciot__"
HCIOT_RUNTIME_SETTINGS_ATTR = "hciot_runtime_settings_by_prompt"
HCIOT_PERSONA_ATTR = "hciot_persona_by_prompt"
__all__ = [
    "RULE_SECTION_FIELDS",
    "SYSTEM_DEFAULT_PROMPT_ID",
    "RuleSections",
    "WelcomeBlock",
    "HciotRuntimeSettings",
    "HCIOT_STORE_NAME",
    "get_available_tts_characters",
    "load_runtime_settings_from_prompt_manager",
    "save_runtime_settings_to_prompt_manager",
    "get_default_runtime_settings",
]
_TTS_CHARACTER_ENV = "HCIOT_TTS_CHARACTER"
_TTS_CHARACTER_FALLBACK = "healthy2"


def _parse_tts_characters(raw: Optional[str]) -> list[str]:
    source = raw or _TTS_CHARACTER_FALLBACK
    characters = [character.strip() for character in source.split(",") if character.strip()]
    return characters or [_TTS_CHARACTER_FALLBACK]


def get_available_tts_characters() -> list[str]:
    return _parse_tts_characters(os.getenv(_TTS_CHARACTER_ENV, _TTS_CHARACTER_FALLBACK))


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


def get_default_runtime_settings() -> HciotRuntimeSettings:
    return HciotRuntimeSettings()


_runtime_settings_repo = RuntimeSettingsRepo[HciotRuntimeSettings](
    store_name=HCIOT_STORE_NAME,
    settings_type=HciotRuntimeSettings,
    default_settings_factory=get_default_runtime_settings,
    default_max_response_chars=DEFAULT_MAX_RESPONSE_CHARS,
    storage_adapter=FlatRuntimeSettingsAdapter(attr=HCIOT_RUNTIME_SETTINGS_ATTR),
    active_prompt_id_attr="hciot_active_prompt_id",
)


def load_runtime_settings_from_prompt_manager(
    prompt_manager,
    prompt_id: Optional[str] = None,
    store_name: str = HCIOT_STORE_NAME,
) -> HciotRuntimeSettings:
    return _runtime_settings_repo.load_from_prompt_manager(
        prompt_manager,
        prompt_id,
        store_name=store_name,
    )


def save_runtime_settings_to_prompt_manager(
    prompt_manager,
    settings: HciotRuntimeSettings,
    prompt_id: Optional[str] = None,
    store_name: str = HCIOT_STORE_NAME,
) -> str:
    return _runtime_settings_repo.save_to_prompt_manager(
        prompt_manager,
        settings,
        prompt_id,
        store_name=store_name,
    )
