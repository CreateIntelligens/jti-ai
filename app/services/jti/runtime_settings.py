"""JTI runtime settings per prompt: rule sections, welcome text, and length limit."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.services.jti.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    WELCOME_TEXT,
    get_default_response_rule_sections,
)

JTI_STORE_NAME = "__jti__"
SYSTEM_DEFAULT_PROMPT_ID = "system_default"


class RuleSections(BaseModel):
    role_scope: str
    scope_limits: str
    response_style: str
    knowledge_rules: str


class WelcomeBlock(BaseModel):
    title: str
    description: str


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
    max_response_chars: int = Field(default=DEFAULT_MAX_RESPONSE_CHARS, ge=30, le=600)


RULE_SECTION_FIELDS = ("role_scope", "scope_limits", "response_style", "knowledge_rules")


def get_default_runtime_settings() -> JtiRuntimeSettings:
    """Return default runtime settings."""
    return JtiRuntimeSettings()


def _resolve_runtime_prompt_id(store_prompts, prompt_id: Optional[str]) -> str:
    """Resolve runtime profile id. Falls back to active prompt, then system default."""
    if isinstance(prompt_id, str) and prompt_id.strip():
        return prompt_id
    active_prompt_id = getattr(store_prompts, "active_prompt_id", None)
    return active_prompt_id or SYSTEM_DEFAULT_PROMPT_ID


def _load_raw_runtime_settings(store_prompts, prompt_id: str) -> Optional[Dict[str, Any]]:
    """Load raw runtime settings from per-prompt map with legacy fallback."""
    raw_by_prompt = getattr(store_prompts, "jti_runtime_settings_by_prompt", None)
    if isinstance(raw_by_prompt, dict):
        raw_for_prompt = raw_by_prompt.get(prompt_id)
        if isinstance(raw_for_prompt, dict):
            return raw_for_prompt

        raw_for_default = raw_by_prompt.get(SYSTEM_DEFAULT_PROMPT_ID)
        if isinstance(raw_for_default, dict):
            return raw_for_default

    legacy_raw = getattr(store_prompts, "jti_runtime_settings", None)
    if isinstance(legacy_raw, dict):
        return legacy_raw

    return None


def _normalize_runtime_settings(raw: Optional[Dict[str, Any]]) -> JtiRuntimeSettings:
    """Merge persisted raw settings with defaults and coerce into schema."""
    settings = get_default_runtime_settings().model_dump()

    if not isinstance(raw, dict):
        return JtiRuntimeSettings(**settings)

    # 新格式：分段規則
    raw_sections = raw.get("response_rule_sections")
    if isinstance(raw_sections, dict):
        for lang in ("zh", "en"):
            section_data = raw_sections.get(lang)
            if isinstance(section_data, dict):
                for field in RULE_SECTION_FIELDS:
                    if lang == "zh" and field == "role_scope":
                        # ZH 角色與可做事項固定使用程式碼預設，不走可編輯設定。
                        continue
                    value = section_data.get(field)
                    if isinstance(value, str) and value.strip():
                        settings["response_rule_sections"][lang][field] = value

    # 舊格式相容：response_rules[lang] 單一大字串，放入 response_style
    raw_legacy_rules = raw.get("response_rules")
    if isinstance(raw_legacy_rules, dict):
        for lang in ("zh", "en"):
            value = raw_legacy_rules.get(lang)
            if isinstance(value, str) and value.strip():
                settings["response_rule_sections"][lang]["response_style"] = value

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

    return JtiRuntimeSettings(**settings)


def load_runtime_settings_from_prompt_manager(
    prompt_manager,
    prompt_id: Optional[str] = None,
    store_name: str = JTI_STORE_NAME,
) -> JtiRuntimeSettings:
    """Load effective runtime settings from PromptManager."""
    if not prompt_manager:
        return get_default_runtime_settings()

    store_prompts = prompt_manager._load_store_prompts(store_name)
    runtime_prompt_id = _resolve_runtime_prompt_id(store_prompts, prompt_id)
    raw = _load_raw_runtime_settings(store_prompts, runtime_prompt_id)

    try:
        settings = _normalize_runtime_settings(raw)
        # 預設人物設定固定使用程式碼預設值，避免被歷史資料覆蓋。
        if runtime_prompt_id == SYSTEM_DEFAULT_PROMPT_ID:
            settings.max_response_chars = DEFAULT_MAX_RESPONSE_CHARS
        return settings
    except Exception:
        return get_default_runtime_settings()


def save_runtime_settings_to_prompt_manager(
    prompt_manager,
    settings: JtiRuntimeSettings,
    prompt_id: Optional[str] = None,
    store_name: str = JTI_STORE_NAME,
) -> str:
    """Persist runtime settings in PromptManager under JTI store document."""
    store_prompts = prompt_manager._load_store_prompts(store_name)
    runtime_prompt_id = _resolve_runtime_prompt_id(store_prompts, prompt_id)

    runtime_map = getattr(store_prompts, "jti_runtime_settings_by_prompt", None)
    if not isinstance(runtime_map, dict):
        runtime_map = {}
    runtime_map[runtime_prompt_id] = settings.model_dump()
    store_prompts.jti_runtime_settings_by_prompt = runtime_map
    prompt_manager._save_store_prompts(store_prompts)
    return runtime_prompt_id
