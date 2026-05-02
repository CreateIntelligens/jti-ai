"""JTI runtime settings per prompt: rule sections, welcome text, and length limit."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.services._shared.runtime_settings_base import (
    NestedProfileRuntimeSettingsAdapter,
    RULE_SECTION_FIELDS as _RULE_SECTION_FIELDS,
    SYSTEM_DEFAULT_PROMPT_ID as _SYSTEM_DEFAULT_PROMPT_ID,
    RuleSections,
    RuntimeSettingsRepo,
    WelcomeBlock,
)
from app.services.jti.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    PERSONA,
    WELCOME_TEXT,
    get_default_response_rule_sections,
)

JTI_STORE_NAME = "__jti__"
JTI_PROFILES_ATTR = "jti_profiles_by_prompt"
PROFILE_PERSONA_KEY = "persona"
PROFILE_RUNTIME_KEY = "runtime_settings"
RULE_SECTION_FIELDS = _RULE_SECTION_FIELDS
SYSTEM_DEFAULT_PROMPT_ID = _SYSTEM_DEFAULT_PROMPT_ID


class JtiRuntimeSettings(BaseModel):
    response_rule_sections: Dict[str, RuleSections] = Field(
        default_factory=lambda: {
            "zh": RuleSections(**get_default_response_rule_sections()["zh"]),
            "en": RuleSections(**get_default_response_rule_sections()["en"]),
        }
    )
    welcome: Dict[str, WelcomeBlock] = Field(
        default_factory=lambda: {
            "zh": WelcomeBlock(**WELCOME_TEXT["zh"]),
            "en": WelcomeBlock(**WELCOME_TEXT["en"]),
        }
    )
    # 0 = 不限制字數（由前端/使用者可選）
    max_response_chars: int = Field(default=DEFAULT_MAX_RESPONSE_CHARS, ge=0, le=600)


def get_default_runtime_settings() -> JtiRuntimeSettings:
    """Return default runtime settings."""
    return JtiRuntimeSettings()


def _default_persona_pair() -> Dict[str, str]:
    zh = PERSONA.get("zh", "")
    return {
        "zh": zh,
        "en": PERSONA.get("en", zh),
    }


_runtime_settings_repo = RuntimeSettingsRepo[JtiRuntimeSettings](
    store_name=JTI_STORE_NAME,
    settings_type=JtiRuntimeSettings,
    default_settings_factory=get_default_runtime_settings,
    default_max_response_chars=DEFAULT_MAX_RESPONSE_CHARS,
    storage_adapter=NestedProfileRuntimeSettingsAdapter(
        attr=JTI_PROFILES_ATTR,
        runtime_key=PROFILE_RUNTIME_KEY,
        persona_key=PROFILE_PERSONA_KEY,
        default_persona_factory=_default_persona_pair,
    ),
    include_legacy_response_rules=True,
)


def load_runtime_settings_from_prompt_manager(
    prompt_manager,
    prompt_id: Optional[str] = None,
    store_name: str = JTI_STORE_NAME,
) -> JtiRuntimeSettings:
    """Load effective runtime settings from PromptManager."""
    return _runtime_settings_repo.load_from_prompt_manager(
        prompt_manager,
        prompt_id,
        store_name=store_name,
    )


def save_runtime_settings_to_prompt_manager(
    prompt_manager,
    settings: JtiRuntimeSettings,
    prompt_id: Optional[str] = None,
    store_name: str = JTI_STORE_NAME,
) -> str:
    """Persist runtime settings in PromptManager under JTI store document."""
    return _runtime_settings_repo.save_to_prompt_manager(
        prompt_manager,
        settings,
        prompt_id,
        store_name=store_name,
    )
