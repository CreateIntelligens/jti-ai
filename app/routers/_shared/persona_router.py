"""共用 Persona 管理 router factory。

JTI / HCIoT 幾乎一樣的 CRUD + runtime-settings 流程。差異透過 PersonaRouterConfig
注入：store 名稱、預設/自訂名稱、字數限制、runtime-settings 型別、以及
兩種 persona 儲存格式（JTI 嵌套於 profiles_by_prompt[id][key]，
HCIoT 扁平於 persona_by_prompt[id]）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple, Type

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_admin
from app.services.agent_utils import normalize_language as _normalize_language
import app.deps as deps

SUPPORTED_LANGUAGES = ("zh", "en")


class PersonaStorageAdapter:
    """抽象 persona 資料在 store_prompts 上的讀寫方式。"""

    def get(self, store_prompts, prompt_id: str) -> Optional[Dict[str, str]]:
        raise NotImplementedError

    def set(self, store_prompts, prompt_id: str, pair: Dict[str, str]) -> None:
        raise NotImplementedError

    def remove(self, store_prompts, prompt_id: str) -> bool:
        raise NotImplementedError


class FlatPersonaAdapter(PersonaStorageAdapter):
    """HCIoT 格式：store_prompts.<attr>[prompt_id] = {"zh": ..., "en": ...}"""

    def __init__(self, attr: str):
        self.attr = attr

    def _load_map(self, store_prompts) -> Dict[str, Dict[str, str]]:
        raw = getattr(store_prompts, self.attr, None)
        return raw if isinstance(raw, dict) else {}

    def get(self, store_prompts, prompt_id):
        raw = self._load_map(store_prompts).get(prompt_id)
        return raw if isinstance(raw, dict) else None

    def set(self, store_prompts, prompt_id, pair):
        mapping = self._load_map(store_prompts)
        mapping[prompt_id] = pair
        setattr(store_prompts, self.attr, mapping)

    def remove(self, store_prompts, prompt_id):
        mapping = getattr(store_prompts, self.attr, None)
        if isinstance(mapping, dict) and prompt_id in mapping:
            mapping.pop(prompt_id)
            setattr(store_prompts, self.attr, mapping)
            return True
        return False


class NestedProfilePersonaAdapter(PersonaStorageAdapter):
    """JTI 格式：store_prompts.<attr>[prompt_id][<key>] = {"zh": ..., "en": ...}"""

    def __init__(self, attr: str, key: str):
        self.attr = attr
        self.key = key

    def _load_map(self, store_prompts) -> Dict[str, Dict]:
        raw = getattr(store_prompts, self.attr, None)
        return raw if isinstance(raw, dict) else {}

    def get(self, store_prompts, prompt_id):
        profile = self._load_map(store_prompts).get(prompt_id)
        if not isinstance(profile, dict):
            return None
        pair = profile.get(self.key)
        return pair if isinstance(pair, dict) else None

    def set(self, store_prompts, prompt_id, pair):
        mapping = self._load_map(store_prompts)
        profile = mapping.get(prompt_id)
        if not isinstance(profile, dict):
            profile = {}
        profile[self.key] = pair
        mapping[prompt_id] = profile
        setattr(store_prompts, self.attr, mapping)

    def remove(self, store_prompts, prompt_id):
        mapping = getattr(store_prompts, self.attr, None)
        if isinstance(mapping, dict) and prompt_id in mapping:
            mapping.pop(prompt_id)
            setattr(store_prompts, self.attr, mapping)
            return True
        return False


RuntimeLoader = Callable[..., Any]
RuntimeSaver = Callable[..., Any]


@dataclass
class PersonaRouterConfig:
    tag: str
    store_name_zh: str
    store_name_en: str
    system_default_prompt_id: str
    persona_defaults: Dict[str, str]
    default_prompt_names: Dict[str, str]
    custom_prompt_name_prefix: Dict[str, str]
    persona_adapter: PersonaStorageAdapter
    runtime_settings_type: Type[BaseModel]
    runtime_settings_load: RuntimeLoader
    runtime_settings_save: RuntimeSaver
    runtime_settings_rule_section_fields: Tuple[str, ...]
    max_response_chars_ge: int
    max_response_chars_le: int
    main_agent: Any
    # App-specific prompt index attrs (independent from shared prompts[])
    prompt_index_attr: str  # e.g. "hciot_prompt_index"
    active_prompt_id_attr: str  # e.g. "hciot_active_prompt_id"
    max_custom_prompts: int = 3
    clone_success_message: str = "已複製預設人物設定並啟用"
    runtime_update_message: str = "已更新回覆規則"
    runtime_default_readonly_message: str = "預設設定為唯讀，請先建立副本並啟用後再編輯。"
    delete_clears_runtime_overrides: bool = False
    runtime_overrides_attr: Optional[str] = None


class _CreatePromptRequest(BaseModel):
    name: str
    content: str


class _UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None


class _SetActivePromptRequest(BaseModel):
    prompt_id: Optional[str] = None


class _RuntimeWelcomePayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class _RuntimeRuleSectionsPayload(BaseModel):
    """Rule sections — JTI / HCIoT 都用同樣 4 個欄位（見 runtime_settings.RULE_SECTION_FIELDS）。"""

    role_scope: Optional[str] = None
    scope_limits: Optional[str] = None
    response_style: Optional[str] = None
    knowledge_rules: Optional[str] = None


class _UpdateRuntimeSettingsRequestBase(BaseModel):
    prompt_id: Optional[str] = None
    response_rule_sections: Optional[Dict[str, _RuntimeRuleSectionsPayload]] = None
    welcome: Optional[Dict[str, _RuntimeWelcomePayload]] = None
    max_response_chars: Optional[int] = None


def build_persona_router(config: PersonaRouterConfig) -> APIRouter:
    router = APIRouter(tags=[config.tag], dependencies=[Depends(verify_admin)])

    def require_prompt_manager():
        if not deps.prompt_manager:
            raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
        return deps.prompt_manager

    def store_name_for(language: Optional[str]) -> str:
        return config.store_name_en if _normalize_language(language) == "en" else config.store_name_zh

    def default_persona_pair() -> Dict[str, str]:
        zh = config.persona_defaults.get("zh", "")
        en = config.persona_defaults.get("en", zh)
        return {"zh": zh, "en": en}

    def legacy_persona_pair(content: Optional[str]) -> Dict[str, str]:
        base = content or ""
        if base in (config.persona_defaults.get("zh"), config.persona_defaults.get("en")):
            return default_persona_pair()
        return {"zh": base, "en": base}

    def normalize_persona_pair(raw_pair, fallback_content: Optional[str]) -> Dict[str, str]:
        legacy = legacy_persona_pair(fallback_content)
        if not isinstance(raw_pair, dict):
            return legacy
        pair: Dict[str, str] = {}
        for lang in SUPPORTED_LANGUAGES:
            value = raw_pair.get(lang)
            pair[lang] = value if isinstance(value, str) and value.strip() else legacy[lang]
        return pair

    def prompt_content_for_language(
        prompt_id: str,
        fallback_content: Optional[str],
        language: str,
        store_prompts,
    ) -> str:
        lang = _normalize_language(language)
        raw_pair = config.persona_adapter.get(store_prompts, prompt_id)
        pair = normalize_persona_pair(raw_pair, fallback_content)
        return pair.get(lang, pair["zh"])

    def default_prompt_dict(language: str) -> dict:
        lang = _normalize_language(language)
        return {
            "id": config.system_default_prompt_id,
            "name": config.default_prompt_names[lang],
            "content": config.persona_defaults.get(lang, config.persona_defaults.get("zh", "")),
            "created_at": "",
            "updated_at": "",
            "is_default": True,
            "readonly": True,
        }

    def next_custom_prompt_name(prompts, language: str) -> str:
        lang = _normalize_language(language)
        prefix = config.custom_prompt_name_prefix[lang]
        pattern = re.compile(rf"^{re.escape(prefix)}\s+(\d+)$")
        existing_names = {
            p.name.strip()
            for p in prompts
            if isinstance(getattr(p, "name", None), str) and p.name.strip()
        }
        used_indices = set()
        for name in existing_names:
            match = pattern.match(name)
            if match:
                used_indices.add(int(match.group(1)))
        next_index = 1
        candidate = f"{prefix} {next_index}"
        while next_index in used_indices or candidate in existing_names:
            next_index += 1
            candidate = f"{prefix} {next_index}"
        return candidate

    def prompt_order_key(name: str):
        normalized = name.strip()
        for prefix in set(config.custom_prompt_name_prefix.values()):
            pattern = re.compile(rf"^{re.escape(prefix)}\s+(\d+)$")
            match = pattern.match(normalized)
            if match:
                return (0, int(match.group(1)), normalized)
        return (1, normalized)

    def enforce_custom_prompt_limit(prompts):
        if len(prompts) >= config.max_custom_prompts:
            raise HTTPException(
                status_code=400,
                detail=f"自訂人物設定最多 {config.max_custom_prompts} 個",
            )

    def copy_default_runtime(prompt_id: str, store_name: str):
        pm = require_prompt_manager()
        base = config.runtime_settings_load(
            pm,
            config.system_default_prompt_id,
            store_name=store_name,
        )
        config.runtime_settings_save(pm, base, prompt_id=prompt_id, store_name=store_name)

    # --- App-specific index helpers ---

    def _get_index(store_prompts) -> list:
        """Read the app-specific prompt index list."""
        raw = getattr(store_prompts, config.prompt_index_attr, None)
        return list(raw) if isinstance(raw, list) else []

    def _set_index(store_prompts, index: list) -> None:
        """Write the app-specific prompt index list."""
        setattr(store_prompts, config.prompt_index_attr, index)

    def _get_app_active_id(store_prompts) -> Optional[str]:
        """Read the app-specific active_prompt_id."""
        return getattr(store_prompts, config.active_prompt_id_attr, None)

    def _set_app_active_id(store_prompts, prompt_id: Optional[str]) -> None:
        """Write the app-specific active_prompt_id."""
        setattr(store_prompts, config.active_prompt_id_attr, prompt_id)

    def _find_index_position(index: list, prompt_id: str) -> Optional[int]:
        return next((i for i, entry in enumerate(index) if entry.id == prompt_id), None)

    def _find_index_entry(index: list, prompt_id: str):
        position = _find_index_position(index, prompt_id)
        return index[position] if position is not None else None

    def validate_and_resolve_prompt_id(requested: Optional[str], store_name: str) -> str:
        if requested:
            if requested == config.system_default_prompt_id:
                return config.system_default_prompt_id
            pm = require_prompt_manager()
            store_prompts = pm.get_store_prompts(store_name)
            index = _get_index(store_prompts)
            if _find_index_entry(index, requested) is None:
                raise HTTPException(status_code=404, detail="人物設定不存在")
            return requested
        if not deps.prompt_manager:
            return config.system_default_prompt_id
        store_prompts = deps.prompt_manager.get_store_prompts(store_name)
        return _get_app_active_id(store_prompts) or config.system_default_prompt_id

    def merge_runtime_settings(current, request):
        data = current.model_dump()
        if request.response_rule_sections is not None:
            for lang in SUPPORTED_LANGUAGES:
                section = request.response_rule_sections.get(lang)
                if not section:
                    continue
                for field in config.runtime_settings_rule_section_fields:
                    value = getattr(section, field, None)
                    if isinstance(value, str) and value.strip():
                        data["response_rule_sections"][lang][field] = value
        if request.welcome is not None:
            for lang in SUPPORTED_LANGUAGES:
                block = request.welcome.get(lang)
                if not block:
                    continue
                if isinstance(block.title, str) and block.title.strip():
                    data["welcome"][lang]["title"] = block.title
                if isinstance(block.description, str) and block.description.strip():
                    data["welcome"][lang]["description"] = block.description
        if request.max_response_chars is not None:
            data["max_response_chars"] = request.max_response_chars
        return config.runtime_settings_type(**data)

    @router.get("/")
    def list_prompts(language: str = "zh"):
        lang = _normalize_language(language)
        store_name = store_name_for(lang)
        default_prompt = default_prompt_dict(lang)

        custom_prompts = []
        active_prompt_id = None
        store_prompts = None

        if deps.prompt_manager:
            store_prompts = deps.prompt_manager.get_store_prompts(store_name)
            index = _get_index(store_prompts)
            custom_prompts = [entry.model_dump() for entry in index]
            active_prompt_id = _get_app_active_id(store_prompts)

        for p in custom_prompts:
            p["content"] = prompt_content_for_language(
                p["id"],
                p.get("content"),
                lang,
                store_prompts,
            )
            p["is_default"] = False
            p["readonly"] = False

        default_prompt["is_active"] = not active_prompt_id
        for p in custom_prompts:
            p["is_active"] = p["id"] == active_prompt_id

        custom_prompts.sort(key=lambda p: prompt_order_key(str(p.get("name", ""))))

        return {
            "prompts": [default_prompt] + custom_prompts,
            "active_prompt_id": active_prompt_id,
            "max_custom_prompts": config.max_custom_prompts,
        }

    @router.post("/")
    def create_prompt(request: _CreatePromptRequest, language: str = "zh"):
        pm = require_prompt_manager()
        lang = _normalize_language(language)
        store_name = store_name_for(lang)
        store_prompts = pm.get_store_prompts(store_name)
        index = _get_index(store_prompts)
        enforce_custom_prompt_limit(index)

        from app.prompts import PromptIndexEntry

        entry = PromptIndexEntry(name=request.name)
        index.append(entry)
        _set_index(store_prompts, index)

        persona_pair = default_persona_pair()
        persona_pair[lang] = request.content
        config.persona_adapter.set(store_prompts, entry.id, persona_pair)
        pm.save_store_prompts(store_prompts)

        copy_default_runtime(entry.id, store_name)

        return entry.model_dump()

    @router.post("/clone")
    def clone_default_prompt(language: str = "zh"):
        pm = require_prompt_manager()
        lang = _normalize_language(language)
        store_name = store_name_for(lang)
        store_prompts = pm.get_store_prompts(store_name)
        index = _get_index(store_prompts)
        enforce_custom_prompt_limit(index)

        from app.prompts import PromptIndexEntry

        entry = PromptIndexEntry(name=next_custom_prompt_name(index, lang))
        index.append(entry)
        _set_index(store_prompts, index)
        _set_app_active_id(store_prompts, entry.id)
        config.persona_adapter.set(store_prompts, entry.id, default_persona_pair())
        pm.save_store_prompts(store_prompts)

        copy_default_runtime(entry.id, store_name)

        config.main_agent.remove_all_sessions()
        return {"prompt": entry.model_dump(), "message": config.clone_success_message}

    @router.put("/{prompt_id}")
    def update_prompt(prompt_id: str, request: _UpdatePromptRequest, language: str = "zh"):
        if prompt_id == config.system_default_prompt_id:
            raise HTTPException(
                status_code=403,
                detail="預設人物設定為唯讀，無法修改。請先建立副本。",
            )
        pm = require_prompt_manager()
        lang = _normalize_language(language)
        store_name = store_name_for(lang)
        store_prompts = pm.get_store_prompts(store_name)
        index = _get_index(store_prompts)
        entry_idx = _find_index_position(index, prompt_id)
        if entry_idx is None:
            raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} 不存在")

        entry = index[entry_idx]
        if request.name is not None:
            entry.name = request.name

        persona_pair = normalize_persona_pair(
            config.persona_adapter.get(store_prompts, prompt_id),
            None,
        )
        if request.content is not None:
            persona_pair[lang] = request.content
            config.persona_adapter.set(store_prompts, prompt_id, persona_pair)

        entry.updated_at = datetime.now(timezone.utc).isoformat()
        index[entry_idx] = entry
        _set_index(store_prompts, index)
        pm.save_store_prompts(store_prompts)

        payload = entry.model_dump()
        payload["content"] = persona_pair.get(lang, "")
        return payload

    @router.delete("/{prompt_id}")
    def delete_prompt(prompt_id: str, language: str = "zh"):
        if prompt_id == config.system_default_prompt_id:
            raise HTTPException(status_code=403, detail="預設人物設定無法刪除")

        pm = require_prompt_manager()
        store_name = store_name_for(language)
        store_prompts = pm.get_store_prompts(store_name)
        index = _get_index(store_prompts)
        if _find_index_entry(index, prompt_id) is None:
            raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} 不存在")
        index = [entry for entry in index if entry.id != prompt_id]

        # Clear active if deleted prompt was active
        if _get_app_active_id(store_prompts) == prompt_id:
            _set_app_active_id(store_prompts, index[0].id if index else None)

        _set_index(store_prompts, index)
        config.persona_adapter.remove(store_prompts, prompt_id)

        if config.delete_clears_runtime_overrides and config.runtime_overrides_attr:
            overrides = getattr(store_prompts, config.runtime_overrides_attr, None)
            if isinstance(overrides, dict) and prompt_id in overrides:
                overrides.pop(prompt_id)
                setattr(store_prompts, config.runtime_overrides_attr, overrides)

        pm.save_store_prompts(store_prompts)
        return {"message": "人物設定已刪除"}

    @router.post("/active")
    def set_active_prompt(request: _SetActivePromptRequest, language: str = "zh"):
        pm = require_prompt_manager()
        store_name = store_name_for(language)
        store_prompts = pm.get_store_prompts(store_name)

        if request.prompt_id and request.prompt_id != config.system_default_prompt_id:
            index = _get_index(store_prompts)
            if _find_index_entry(index, request.prompt_id) is None:
                raise HTTPException(status_code=404, detail="人物設定不存在")
            _set_app_active_id(store_prompts, request.prompt_id)
        else:
            _set_app_active_id(store_prompts, None)

        pm.save_store_prompts(store_prompts)
        config.main_agent.remove_all_sessions()
        return {"message": "已設定啟用的人物設定", "prompt_id": request.prompt_id}

    @router.get("/active")
    def get_active_prompt(language: str = "zh"):
        pm = require_prompt_manager()
        lang = _normalize_language(language)
        store_name = store_name_for(lang)
        store_prompts = pm.get_store_prompts(store_name)
        active_id = _get_app_active_id(store_prompts)
        if not active_id:
            return {"prompt": default_prompt_dict(language), "is_default": True}

        index = _get_index(store_prompts)
        entry = _find_index_entry(index, active_id)
        if not entry:
            return {"prompt": default_prompt_dict(language), "is_default": True}

        payload = entry.model_dump()
        payload["content"] = prompt_content_for_language(
            entry.id, None, lang, store_prompts,
        )
        return {"prompt": payload, "is_default": False}

    @router.get("/runtime-settings")
    def get_runtime_settings(prompt_id: Optional[str] = None, language: str = "zh"):
        store_name = store_name_for(language)
        runtime_prompt_id = validate_and_resolve_prompt_id(prompt_id, store_name)
        settings = config.runtime_settings_load(
            deps.prompt_manager,
            runtime_prompt_id,
            store_name=store_name,
        )
        return {"prompt_id": runtime_prompt_id, "settings": settings.model_dump()}

    @router.post("/runtime-settings")
    def update_runtime_settings(
        request: _UpdateRuntimeSettingsRequestBase = Body(...),
        language: str = "zh",
    ):
        if request.max_response_chars is not None:
            ge = config.max_response_chars_ge
            le = config.max_response_chars_le
            if not ge <= request.max_response_chars <= le:
                raise HTTPException(
                    status_code=422,
                    detail=f"max_response_chars must be between {ge} and {le}",
                )
        pm = require_prompt_manager()
        store_name = store_name_for(language)
        runtime_prompt_id = validate_and_resolve_prompt_id(request.prompt_id, store_name)
        if runtime_prompt_id == config.system_default_prompt_id:
            raise HTTPException(status_code=403, detail=config.runtime_default_readonly_message)

        current = config.runtime_settings_load(pm, runtime_prompt_id, store_name=store_name)
        updated = merge_runtime_settings(current, request)
        config.runtime_settings_save(
            pm, updated, prompt_id=runtime_prompt_id, store_name=store_name
        )
        config.main_agent.remove_all_sessions()
        return {
            "message": config.runtime_update_message,
            "prompt_id": runtime_prompt_id,
            "settings": updated.model_dump(),
        }

    return router
