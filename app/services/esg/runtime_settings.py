"""ESG runtime settings per dedicated persona."""

from __future__ import annotations

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
from app.services.esg.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    DEFAULT_RESPONSE_RULE_SECTIONS,
    WELCOME_TEXT,
)

ESG_STORE_NAME = "__esg__"
ESG_RUNTIME_SETTINGS_ATTR = "esg_runtime_settings_by_prompt"
ESG_PERSONA_ATTR = "esg_persona_by_prompt"

__all__ = [
    "RULE_SECTION_FIELDS",
    "SYSTEM_DEFAULT_PROMPT_ID",
    "RuleSections",
    "WelcomeBlock",
    "EsgRuntimeSettings",
    "ESG_STORE_NAME",
    "load_runtime_settings_from_prompt_manager",
    "save_runtime_settings_to_prompt_manager",
    "get_default_runtime_settings",
]


class EsgRuntimeSettings(BaseModel):
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
    max_response_chars: int = Field(default=DEFAULT_MAX_RESPONSE_CHARS, ge=0, le=600)


def get_default_runtime_settings() -> EsgRuntimeSettings:
    return EsgRuntimeSettings()


_runtime_settings_repo = RuntimeSettingsRepo[EsgRuntimeSettings](
    store_name=ESG_STORE_NAME,
    settings_type=EsgRuntimeSettings,
    default_settings_factory=get_default_runtime_settings,
    default_max_response_chars=DEFAULT_MAX_RESPONSE_CHARS,
    storage_adapter=FlatRuntimeSettingsAdapter(attr=ESG_RUNTIME_SETTINGS_ATTR),
    active_prompt_id_attr="esg_active_prompt_id",
)


def load_runtime_settings_from_prompt_manager(
    prompt_manager,
    prompt_id: Optional[str] = None,
    store_name: str = ESG_STORE_NAME,
) -> EsgRuntimeSettings:
    return _runtime_settings_repo.load_from_prompt_manager(
        prompt_manager,
        prompt_id,
        store_name=store_name,
    )


def save_runtime_settings_to_prompt_manager(
    prompt_manager,
    settings: EsgRuntimeSettings,
    prompt_id: Optional[str] = None,
    store_name: str = ESG_STORE_NAME,
) -> str:
    return _runtime_settings_repo.save_to_prompt_manager(
        prompt_manager,
        settings,
        prompt_id,
        store_name=store_name,
    )
