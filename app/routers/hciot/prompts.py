"""
HCIoT persona management API endpoints.
"""

import re
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_admin, verify_auth
from app.services.hciot.agent_prompts import PERSONA
from app.services.hciot.main_agent import main_agent
from app.services.hciot.runtime_settings import (
    HciotRuntimeSettings,
    RULE_SECTION_FIELDS,
    SYSTEM_DEFAULT_PROMPT_ID,
    load_runtime_settings_from_prompt_manager,
    save_runtime_settings_to_prompt_manager,
)
import app.deps as deps

router = APIRouter(tags=["HCIoT Prompts"], dependencies=[Depends(verify_admin)])

HCIOT_STORE_NAME_ZH = "__hciot__"
HCIOT_STORE_NAME_EN = "__hciot__en"
SYSTEM_DEFAULT_ID = SYSTEM_DEFAULT_PROMPT_ID
MAX_CUSTOM_PROMPTS = 3
DEFAULT_PROMPT_NAMES = {
    "zh": "預設衛教助手設定",
    "en": "Default Education Assistant",
}
CUSTOM_PROMPT_NAME_PREFIX = {
    "zh": "自訂衛教助手設定",
    "en": "Custom Education Assistant",
}


class CreatePromptRequest(BaseModel):
    name: str
    content: str


class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None


class SetActivePromptRequest(BaseModel):
    prompt_id: Optional[str] = None


class RuntimeWelcomePayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class RuntimeRuleSectionsPayload(BaseModel):
    role_scope: Optional[str] = None
    scope_limits: Optional[str] = None
    response_style: Optional[str] = None
    knowledge_rules: Optional[str] = None


class UpdateRuntimeSettingsRequest(BaseModel):
    prompt_id: Optional[str] = None
    response_rule_sections: Optional[Dict[str, RuntimeRuleSectionsPayload]] = None
    welcome: Optional[Dict[str, RuntimeWelcomePayload]] = None
    max_response_chars: Optional[int] = Field(default=None, ge=30, le=100)


def _normalize_language(language: Optional[str]) -> str:
    if not isinstance(language, str):
        return "zh"
    normalized = language.strip().lower()
    return "en" if normalized.startswith("en") else "zh"


def _get_store_name_for_language(language: Optional[str]) -> str:
    return HCIOT_STORE_NAME_EN if _normalize_language(language) == "en" else HCIOT_STORE_NAME_ZH


def _get_default_prompt_dict(language: str = "zh") -> dict:
    lang = _normalize_language(language)
    return {
        "id": SYSTEM_DEFAULT_ID,
        "name": DEFAULT_PROMPT_NAMES[lang],
        "content": PERSONA.get(lang, PERSONA["zh"]),
        "created_at": "",
        "updated_at": "",
        "is_default": True,
        "readonly": True,
    }


def _get_default_persona_pair() -> Dict[str, str]:
    return {
        "zh": PERSONA.get("zh", ""),
        "en": PERSONA.get("en", PERSONA.get("zh", "")),
    }


def _next_custom_prompt_name(prompts, language: str) -> str:
    lang = _normalize_language(language)
    prefix = CUSTOM_PROMPT_NAME_PREFIX[lang]
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


def _prompt_order_key(name: str):
    normalized = name.strip()
    for prefix in set(CUSTOM_PROMPT_NAME_PREFIX.values()):
        pattern = re.compile(rf"^{re.escape(prefix)}\s+(\d+)$")
        match = pattern.match(normalized)
        if match:
            return (0, int(match.group(1)), normalized)
    return (1, normalized)


def _build_legacy_persona_pair(content: Optional[str]) -> Dict[str, str]:
    base_content = content or ""
    if base_content in (PERSONA.get("zh"), PERSONA.get("en")):
        return _get_default_persona_pair()
    return {"zh": base_content, "en": base_content}


def _get_persona_map(store_prompts) -> Dict[str, Dict[str, str]]:
    raw = getattr(store_prompts, "hciot_persona_by_prompt", None)
    return raw if isinstance(raw, dict) else {}


def _normalize_persona_pair(raw_pair, fallback_content: Optional[str]) -> Dict[str, str]:
    legacy_pair = _build_legacy_persona_pair(fallback_content)
    if not isinstance(raw_pair, dict):
        return legacy_pair

    pair: Dict[str, str] = {}
    for lang in ("zh", "en"):
        value = raw_pair.get(lang)
        pair[lang] = value if isinstance(value, str) and value.strip() else legacy_pair[lang]
    return pair


def _get_prompt_content_for_language(
    prompt_id: str,
    fallback_content: Optional[str],
    language: str,
    persona_map: Dict[str, Dict[str, str]],
) -> str:
    lang = _normalize_language(language)
    pair = _normalize_persona_pair(persona_map.get(prompt_id), fallback_content)
    return pair.get(lang, pair["zh"])


def _merge_runtime_settings(
    current: HciotRuntimeSettings,
    request: UpdateRuntimeSettingsRequest,
) -> HciotRuntimeSettings:
    data = current.model_dump()

    if request.response_rule_sections is not None:
        for lang in ("zh", "en"):
            section = request.response_rule_sections.get(lang)
            if not section:
                continue
            for field in RULE_SECTION_FIELDS:
                value = getattr(section, field, None)
                if isinstance(value, str) and value.strip():
                    data["response_rule_sections"][lang][field] = value

    if request.welcome is not None:
        for lang in ("zh", "en"):
            block = request.welcome.get(lang)
            if not block:
                continue
            if isinstance(block.title, str) and block.title.strip():
                data["welcome"][lang]["title"] = block.title
            if isinstance(block.description, str) and block.description.strip():
                data["welcome"][lang]["description"] = block.description

    if request.max_response_chars is not None:
        data["max_response_chars"] = request.max_response_chars

    return HciotRuntimeSettings(**data)


def _validate_and_resolve_prompt_id(requested_prompt_id: Optional[str], store_name: str) -> str:
    if requested_prompt_id:
        if requested_prompt_id == SYSTEM_DEFAULT_ID:
            return SYSTEM_DEFAULT_ID
        if not deps.prompt_manager:
            raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
        prompt = deps.prompt_manager.get_prompt(store_name, requested_prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="人物設定不存在")
        return requested_prompt_id

    if not deps.prompt_manager:
        return SYSTEM_DEFAULT_ID

    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    return store_prompts.active_prompt_id or SYSTEM_DEFAULT_ID


@router.get("/")
def list_hciot_prompts(language: str = "zh", auth: dict = Depends(verify_auth)):
    lang = _normalize_language(language)
    store_name = _get_store_name_for_language(lang)
    default_prompt = _get_default_prompt_dict(lang)

    custom_prompts = []
    active_prompt_id = None
    persona_map: Dict[str, Dict[str, str]] = {}

    if deps.prompt_manager:
        store_prompts = deps.prompt_manager._load_store_prompts(store_name)
        custom_prompts = [p.model_dump() for p in store_prompts.prompts]
        active_prompt_id = store_prompts.active_prompt_id
        persona_map = _get_persona_map(store_prompts)

    for prompt in custom_prompts:
        prompt["content"] = _get_prompt_content_for_language(
            prompt["id"],
            prompt.get("content"),
            lang,
            persona_map,
        )
        prompt["is_default"] = False
        prompt["readonly"] = False

    default_prompt["is_active"] = not active_prompt_id
    for prompt in custom_prompts:
        prompt["is_active"] = prompt["id"] == active_prompt_id

    custom_prompts.sort(key=lambda p: _prompt_order_key(str(p.get("name", ""))))

    return {
        "prompts": [default_prompt] + custom_prompts,
        "active_prompt_id": active_prompt_id,
        "max_custom_prompts": MAX_CUSTOM_PROMPTS,
    }


@router.post("/")
def create_hciot_prompt(
    request: CreatePromptRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    lang = _normalize_language(language)
    store_name = _get_store_name_for_language(lang)
    prompts = deps.prompt_manager.list_prompts(store_name)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(status_code=400, detail=f"自訂人物設定最多 {MAX_CUSTOM_PROMPTS} 個")

    from app.prompts import Prompt

    new_prompt = Prompt(name=request.name, content=request.content)
    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    store_prompts.prompts.append(new_prompt)

    default_pair = _get_default_persona_pair()
    persona_pair = {"zh": default_pair["zh"], "en": default_pair["en"]}
    persona_pair[lang] = request.content

    persona_map = _get_persona_map(store_prompts)
    persona_map[new_prompt.id] = persona_pair
    store_prompts.hciot_persona_by_prompt = persona_map
    deps.prompt_manager._save_store_prompts(store_prompts)

    base_runtime = load_runtime_settings_from_prompt_manager(
        deps.prompt_manager,
        SYSTEM_DEFAULT_ID,
        store_name=store_name,
    )
    save_runtime_settings_to_prompt_manager(
        deps.prompt_manager,
        base_runtime,
        prompt_id=new_prompt.id,
        store_name=store_name,
    )

    return new_prompt.model_dump()


@router.post("/clone")
def clone_default_prompt(language: str = "zh", auth: dict = Depends(verify_auth)):
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    lang = _normalize_language(language)
    store_name = _get_store_name_for_language(lang)
    prompts = deps.prompt_manager.list_prompts(store_name)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(status_code=400, detail=f"自訂人物設定最多 {MAX_CUSTOM_PROMPTS} 個")

    from app.prompts import Prompt

    clone = Prompt(
        name=_next_custom_prompt_name(prompts, lang),
        content=PERSONA.get(lang, PERSONA["zh"]),
    )

    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    store_prompts.prompts.append(clone)
    store_prompts.active_prompt_id = clone.id

    persona_map = _get_persona_map(store_prompts)
    persona_map[clone.id] = _get_default_persona_pair()
    store_prompts.hciot_persona_by_prompt = persona_map
    deps.prompt_manager._save_store_prompts(store_prompts)

    base_runtime = load_runtime_settings_from_prompt_manager(
        deps.prompt_manager,
        SYSTEM_DEFAULT_ID,
        store_name=store_name,
    )
    save_runtime_settings_to_prompt_manager(
        deps.prompt_manager,
        base_runtime,
        prompt_id=clone.id,
        store_name=store_name,
    )

    main_agent.remove_all_sessions()
    return {"prompt": clone.model_dump(), "message": "已複製預設衛教助手設定並啟用"}


@router.put("/{prompt_id}")
def update_hciot_prompt(
    prompt_id: str,
    request: UpdatePromptRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設人物設定為唯讀，無法修改。請先建立副本。")

    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    lang = _normalize_language(language)
    store_name = _get_store_name_for_language(lang)
    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    prompt_index = next((i for i, p in enumerate(store_prompts.prompts) if p.id == prompt_id), None)
    if prompt_index is None:
        raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} 不存在")

    prompt = store_prompts.prompts[prompt_index]
    if request.name is not None:
        prompt.name = request.name

    persona_map = _get_persona_map(store_prompts)
    persona_pair = _normalize_persona_pair(persona_map.get(prompt_id), prompt.content)
    if request.content is not None:
        persona_pair[lang] = request.content
        persona_map[prompt_id] = persona_pair
        store_prompts.hciot_persona_by_prompt = persona_map

    prompt.content = persona_pair.get(lang, prompt.content)
    prompt.updated_at = datetime.utcnow().isoformat()
    store_prompts.prompts[prompt_index] = prompt
    deps.prompt_manager._save_store_prompts(store_prompts)

    payload = prompt.model_dump()
    payload["content"] = persona_pair.get(lang, payload.get("content", ""))
    return payload


@router.delete("/{prompt_id}")
def delete_hciot_prompt(prompt_id: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設人物設定無法刪除")

    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)

    try:
        deps.prompt_manager.delete_prompt(store_name, prompt_id)
        store_prompts = deps.prompt_manager._load_store_prompts(store_name)
        changed = False

        runtime_map = getattr(store_prompts, "hciot_runtime_settings_by_prompt", None)
        if isinstance(runtime_map, dict) and prompt_id in runtime_map:
            runtime_map.pop(prompt_id, None)
            store_prompts.hciot_runtime_settings_by_prompt = runtime_map
            changed = True

        persona_map = getattr(store_prompts, "hciot_persona_by_prompt", None)
        if isinstance(persona_map, dict) and prompt_id in persona_map:
            persona_map.pop(prompt_id, None)
            store_prompts.hciot_persona_by_prompt = persona_map
            changed = True

        if changed:
            deps.prompt_manager._save_store_prompts(store_prompts)

        return {"message": "人物設定已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/active")
def set_active_hciot_prompt(
    request: SetActivePromptRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)

    try:
        if request.prompt_id and request.prompt_id != SYSTEM_DEFAULT_ID:
            deps.prompt_manager.set_active_prompt(store_name, request.prompt_id)
        else:
            deps.prompt_manager.clear_active_prompt(store_name)

        main_agent.remove_all_sessions()
        return {"message": "已設定啟用的人物設定", "prompt_id": request.prompt_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/active")
def get_active_hciot_prompt(language: str = "zh", auth: dict = Depends(verify_auth)):
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)
    prompt = deps.prompt_manager.get_active_prompt(store_name)
    if not prompt:
        return {"prompt": _get_default_prompt_dict(language), "is_default": True}

    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    persona_map = _get_persona_map(store_prompts)
    lang = _normalize_language(language)

    payload = prompt.model_dump()
    payload["content"] = _get_prompt_content_for_language(
        prompt.id,
        prompt.content,
        lang,
        persona_map,
    )
    return {"prompt": payload, "is_default": False}


@router.get("/runtime-settings")
def get_runtime_settings(
    prompt_id: Optional[str] = None,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    store_name = _get_store_name_for_language(language)
    runtime_prompt_id = _validate_and_resolve_prompt_id(prompt_id, store_name)
    settings = load_runtime_settings_from_prompt_manager(
        deps.prompt_manager,
        runtime_prompt_id,
        store_name=store_name,
    )
    return {"prompt_id": runtime_prompt_id, "settings": settings.model_dump()}


@router.post("/runtime-settings")
def update_runtime_settings(
    request: UpdateRuntimeSettingsRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)
    runtime_prompt_id = _validate_and_resolve_prompt_id(request.prompt_id, store_name)
    if runtime_prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設設定為唯讀，請先建立副本並啟用後再編輯。")

    current = load_runtime_settings_from_prompt_manager(
        deps.prompt_manager,
        runtime_prompt_id,
        store_name=store_name,
    )
    updated = _merge_runtime_settings(current, request)
    save_runtime_settings_to_prompt_manager(
        deps.prompt_manager,
        updated,
        prompt_id=runtime_prompt_id,
        store_name=store_name,
    )
    main_agent.remove_all_sessions()
    return {"message": "已更新回覆規則", "prompt_id": runtime_prompt_id, "settings": updated.model_dump()}
