"""Shared runtime-settings repository helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

SYSTEM_DEFAULT_PROMPT_ID = "system_default"
SUPPORTED_LANGUAGES = ("zh", "en")
RULE_SECTION_FIELDS = ("role_scope", "scope_limits", "response_style", "knowledge_rules")


class RuleSections(BaseModel):
    role_scope: str
    scope_limits: str
    response_style: str
    knowledge_rules: str


class WelcomeBlock(BaseModel):
    title: str
    description: str


RuntimeSettingsModel = TypeVar("RuntimeSettingsModel", bound=BaseModel)
RuntimeSettingsFactory = Callable[[], RuntimeSettingsModel]


def _resolve_runtime_prompt_id(
    store_prompts,
    prompt_id: Optional[str],
    system_default_prompt_id: str = SYSTEM_DEFAULT_PROMPT_ID,
) -> str:
    """Resolve runtime profile id. Falls back to active prompt, then system default."""
    if isinstance(prompt_id, str) and prompt_id.strip():
        return prompt_id
    active_prompt_id = getattr(store_prompts, "active_prompt_id", None)
    return active_prompt_id or system_default_prompt_id


def _normalize_runtime_settings(
    raw: Optional[Dict[str, Any]],
    *,
    settings_type: Type[RuntimeSettingsModel],
    default_settings_factory: RuntimeSettingsFactory[RuntimeSettingsModel],
    include_legacy_response_rules: bool = False,
) -> RuntimeSettingsModel:
    """Merge persisted raw settings with defaults and coerce into the target schema."""
    settings = default_settings_factory().model_dump()

    if not isinstance(raw, dict):
        return settings_type(**settings)

    raw_sections = raw.get("response_rule_sections")
    if isinstance(raw_sections, dict):
        for lang in SUPPORTED_LANGUAGES:
            section_data = raw_sections.get(lang)
            section_settings = settings["response_rule_sections"][lang]
            if isinstance(section_data, dict):
                for field in RULE_SECTION_FIELDS:
                    value = section_data.get(field)
                    if isinstance(value, str) and value.strip():
                        section_settings[field] = value

    if include_legacy_response_rules:
        raw_legacy_rules = raw.get("response_rules")
        if isinstance(raw_legacy_rules, dict):
            for lang in SUPPORTED_LANGUAGES:
                value = raw_legacy_rules.get(lang)
                if isinstance(value, str) and value.strip():
                    settings["response_rule_sections"][lang]["response_style"] = value

    raw_welcome = raw.get("welcome")
    if isinstance(raw_welcome, dict):
        for lang in SUPPORTED_LANGUAGES:
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

    return settings_type(**settings)


class RuntimeSettingsStorageAdapter:
    """Abstract runtime-settings storage format on StorePrompts."""

    def load_raw(
        self,
        store_prompts,
        prompt_id: str,
        system_default_prompt_id: str,
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def save_raw(
        self,
        store_prompts,
        prompt_id: str,
        settings_data: Dict[str, Any],
    ) -> None:
        raise NotImplementedError


class FlatRuntimeSettingsAdapter(RuntimeSettingsStorageAdapter):
    """Flat format: store_prompts.<attr>[prompt_id] = runtime settings."""

    def __init__(self, attr: str):
        self.attr = attr

    def _load_map(self, store_prompts) -> Dict[str, Dict[str, Any]]:
        raw = getattr(store_prompts, self.attr, None)
        return raw if isinstance(raw, dict) else {}

    def load_raw(self, store_prompts, prompt_id, system_default_prompt_id):
        raw_by_prompt = self._load_map(store_prompts)
        raw_for_prompt = raw_by_prompt.get(prompt_id)
        if isinstance(raw_for_prompt, dict):
            return raw_for_prompt

        raw_for_default = raw_by_prompt.get(system_default_prompt_id)
        if isinstance(raw_for_default, dict):
            return raw_for_default

        return None

    def save_raw(self, store_prompts, prompt_id, settings_data):
        runtime_map = self._load_map(store_prompts)
        runtime_map[prompt_id] = settings_data
        setattr(store_prompts, self.attr, runtime_map)


class NestedProfileRuntimeSettingsAdapter(RuntimeSettingsStorageAdapter):
    """Nested profile format: store_prompts.<attr>[prompt_id][<runtime_key>]."""

    def __init__(
        self,
        attr: str,
        runtime_key: str,
        persona_key: Optional[str] = None,
        default_persona_factory: Optional[Callable[[], Dict[str, str]]] = None,
    ):
        self.attr = attr
        self.runtime_key = runtime_key
        self.persona_key = persona_key
        self.default_persona_factory = default_persona_factory

    def _load_map(self, store_prompts) -> Dict[str, Dict[str, Any]]:
        raw = getattr(store_prompts, self.attr, None)
        return raw if isinstance(raw, dict) else {}

    def load_raw(self, store_prompts, prompt_id, system_default_prompt_id):
        profiles = self._load_map(store_prompts)

        for pid in (prompt_id, system_default_prompt_id):
            profile = profiles.get(pid)
            if isinstance(profile, dict):
                raw = profile.get(self.runtime_key)
                if isinstance(raw, dict):
                    return raw

        return None

    def save_raw(self, store_prompts, prompt_id, settings_data):
        profiles_map = self._load_map(store_prompts)
        existing = profiles_map.get(prompt_id)
        profile = existing if isinstance(existing, dict) else {}

        if self.persona_key and self.default_persona_factory:
            profile.setdefault(self.persona_key, self.default_persona_factory())

        profile[self.runtime_key] = settings_data
        profiles_map[prompt_id] = profile
        setattr(store_prompts, self.attr, profiles_map)


@dataclass
class RuntimeSettingsRepo(Generic[RuntimeSettingsModel]):
    """Load/save runtime settings with project-specific storage adapters."""

    store_name: str
    settings_type: Type[RuntimeSettingsModel]
    default_settings_factory: RuntimeSettingsFactory[RuntimeSettingsModel]
    default_max_response_chars: int
    storage_adapter: RuntimeSettingsStorageAdapter
    system_default_prompt_id: str = SYSTEM_DEFAULT_PROMPT_ID
    include_legacy_response_rules: bool = False

    def get_default_runtime_settings(self) -> RuntimeSettingsModel:
        return self.default_settings_factory()

    def resolve_runtime_prompt_id(self, store_prompts, prompt_id: Optional[str]) -> str:
        return _resolve_runtime_prompt_id(
            store_prompts,
            prompt_id,
            self.system_default_prompt_id,
        )

    def load_raw_runtime_settings(
        self,
        store_prompts,
        prompt_id: str,
    ) -> Optional[Dict[str, Any]]:
        return self.storage_adapter.load_raw(
            store_prompts,
            prompt_id,
            self.system_default_prompt_id,
        )

    def normalize_runtime_settings(
        self,
        raw: Optional[Dict[str, Any]],
    ) -> RuntimeSettingsModel:
        return _normalize_runtime_settings(
            raw,
            settings_type=self.settings_type,
            default_settings_factory=self.default_settings_factory,
            include_legacy_response_rules=self.include_legacy_response_rules,
        )

    def load_from_prompt_manager(
        self,
        prompt_manager,
        prompt_id: Optional[str] = None,
        store_name: Optional[str] = None,
    ) -> RuntimeSettingsModel:
        if not prompt_manager:
            return self.get_default_runtime_settings()

        store_prompts = prompt_manager.get_store_prompts(store_name or self.store_name)
        runtime_prompt_id = self.resolve_runtime_prompt_id(store_prompts, prompt_id)
        raw = self.load_raw_runtime_settings(store_prompts, runtime_prompt_id)

        try:
            settings = self.normalize_runtime_settings(raw)
        except ValidationError as e:
            logger.warning(
                "Invalid runtime settings for store=%s prompt=%s, using defaults: %s",
                store_name or self.store_name, runtime_prompt_id, e,
            )
            return self.get_default_runtime_settings()
        if runtime_prompt_id == self.system_default_prompt_id:
            settings.max_response_chars = self.default_max_response_chars
        return settings

    def save_to_prompt_manager(
        self,
        prompt_manager,
        settings: RuntimeSettingsModel,
        prompt_id: Optional[str] = None,
        store_name: Optional[str] = None,
    ) -> str:
        store_prompts = prompt_manager.get_store_prompts(store_name or self.store_name)
        runtime_prompt_id = self.resolve_runtime_prompt_id(store_prompts, prompt_id)

        self.storage_adapter.save_raw(
            store_prompts,
            runtime_prompt_id,
            settings.model_dump(),
        )
        prompt_manager.save_store_prompts(store_prompts)
        return runtime_prompt_id
