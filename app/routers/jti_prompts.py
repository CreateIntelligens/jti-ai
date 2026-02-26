"""
JTI Persona Management API Endpoints

JTI 專用的人物設定管理。
預設人物設定從 agent_prompts.py 讀取（地端唯讀，不存 MongoDB）。
自訂人物設定最多 3 個，存在 MongoDB。
"""

from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.auth import verify_auth
from app.services.jti.main_agent import main_agent
from app.services.jti.agent_prompts import PERSONA
from app.services.jti.runtime_settings import (
    JtiRuntimeSettings,
    load_runtime_settings_from_prompt_manager,
    RULE_SECTION_FIELDS,
    save_runtime_settings_to_prompt_manager,
    SYSTEM_DEFAULT_PROMPT_ID,
)
import app.deps as deps

router = APIRouter(prefix="/api/jti/prompts", tags=["JTI Persona Management"])

JTI_STORE_NAME_ZH = "__jti__"
JTI_STORE_NAME_EN = "__jti__en"
SYSTEM_DEFAULT_ID = SYSTEM_DEFAULT_PROMPT_ID
MAX_CUSTOM_PROMPTS = 3
DEFAULT_PROMPT_NAMES = {
    "zh": "預設人物設定",
    "en": "預設人物設定",
}
CUSTOM_PROMPT_NAME_PREFIX = {
    "zh": "自訂人物設定",
    "en": "自訂人物設定",
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
    max_response_chars: Optional[int] = Field(default=None, ge=30, le=600)


def _normalize_language(language: Optional[str]) -> str:
    if not isinstance(language, str):
        return "zh"
    normalized = language.strip().lower()
    return "en" if normalized.startswith("en") else "zh"


def _get_store_name_for_language(language: Optional[str]) -> str:
    return JTI_STORE_NAME_EN if _normalize_language(language) == "en" else JTI_STORE_NAME_ZH


def _get_default_prompt_dict(language: str = "zh") -> dict:
    """從程式碼取得預設人物設定（唯讀）"""
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


def _build_legacy_persona_pair(content: Optional[str]) -> Dict[str, str]:
    base_content = content or ""
    if base_content in (PERSONA.get("zh"), PERSONA.get("en")):
        return _get_default_persona_pair()
    return {
        "zh": base_content,
        "en": base_content,
    }


def _get_persona_map(store_prompts) -> Dict[str, Dict[str, str]]:
    raw = getattr(store_prompts, "jti_persona_by_prompt", None)
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
    current: JtiRuntimeSettings,
    request: UpdateRuntimeSettingsRequest,
) -> JtiRuntimeSettings:
    data = current.model_dump()

    if request.response_rule_sections is not None:
        for lang in ("zh", "en"):
            section = request.response_rule_sections.get(lang)
            if not section:
                continue
            for field in RULE_SECTION_FIELDS:
                if lang == "zh" and field == "role_scope":
                    # ZH 角色與可做事項固定值，不接受 API 編輯。
                    continue
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

    return JtiRuntimeSettings(**data)


def _validate_and_resolve_prompt_id(requested_prompt_id: Optional[str], store_name: str) -> str:
    """決定 runtime 設定要套用到哪個人物設定。"""
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
def list_jti_prompts(language: str = "zh", auth: dict = Depends(verify_auth)):
    """列出所有 JTI 人物設定（預設 + 自訂）"""
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

    for p in custom_prompts:
        p["content"] = _get_prompt_content_for_language(
            p["id"],
            p.get("content"),
            lang,
            persona_map,
        )
        p["is_default"] = False
        p["readonly"] = False

    if not active_prompt_id:
        default_prompt["is_active"] = True
    else:
        default_prompt["is_active"] = False

    for p in custom_prompts:
        p["is_active"] = (p["id"] == active_prompt_id)

    return {
        "prompts": [default_prompt] + custom_prompts,
        "active_prompt_id": active_prompt_id,
        "max_custom_prompts": MAX_CUSTOM_PROMPTS,
    }


@router.post("/")
def create_jti_prompt(
    request: CreatePromptRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    """建立自訂人物設定（最多 3 個）"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    lang = _normalize_language(language)
    store_name = _get_store_name_for_language(lang)
    prompts = deps.prompt_manager.list_prompts(store_name)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"自訂人物設定最多 {MAX_CUSTOM_PROMPTS} 個",
        )

    from app.prompts import Prompt

    new_prompt = Prompt(name=request.name, content=request.content)
    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    store_prompts.prompts.append(new_prompt)

    default_pair = _get_default_persona_pair()
    persona_pair = {
        "zh": default_pair["zh"],
        "en": default_pair["en"],
    }
    persona_pair[lang] = request.content

    persona_map = _get_persona_map(store_prompts)
    persona_map[new_prompt.id] = persona_pair
    store_prompts.jti_persona_by_prompt = persona_map

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
    """複製預設人物設定為新的自訂人物設定，並自動啟用"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    lang = _normalize_language(language)
    store_name = _get_store_name_for_language(lang)
    prompts = deps.prompt_manager.list_prompts(store_name)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"自訂人物設定最多 {MAX_CUSTOM_PROMPTS} 個",
        )

    from app.prompts import Prompt

    clone = Prompt(
        name=f"{CUSTOM_PROMPT_NAME_PREFIX[lang]} {len(prompts) + 1}",
        content=PERSONA.get(lang, PERSONA["zh"]),
    )

    store_prompts = deps.prompt_manager._load_store_prompts(store_name)
    store_prompts.prompts.append(clone)
    store_prompts.active_prompt_id = clone.id

    persona_map = _get_persona_map(store_prompts)
    persona_map[clone.id] = _get_default_persona_pair()
    store_prompts.jti_persona_by_prompt = persona_map

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

    return {
        "prompt": clone.model_dump(),
        "message": "已複製預設人物設定並啟用",
    }


@router.put("/{prompt_id}")
def update_jti_prompt(
    prompt_id: str,
    request: UpdatePromptRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    """更新人物設定（禁止修改預設）"""
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設人物設定為唯讀，無法修改。請使用「以此為基礎建立副本」功能。")

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
        store_prompts.jti_persona_by_prompt = persona_map

    prompt.content = persona_pair.get(lang, prompt.content)
    prompt.updated_at = datetime.utcnow().isoformat()
    store_prompts.prompts[prompt_index] = prompt
    deps.prompt_manager._save_store_prompts(store_prompts)

    payload = prompt.model_dump()
    payload["content"] = persona_pair.get(lang, payload.get("content", ""))
    return payload


@router.delete("/{prompt_id}")
def delete_jti_prompt(prompt_id: str, language: str = "zh", auth: dict = Depends(verify_auth)):
    """刪除人物設定（禁止刪除預設）"""
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設人物設定無法刪除")

    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)

    try:
        deps.prompt_manager.delete_prompt(store_name, prompt_id)

        store_prompts = deps.prompt_manager._load_store_prompts(store_name)
        changed = False

        runtime_map = getattr(store_prompts, "jti_runtime_settings_by_prompt", None)
        if isinstance(runtime_map, dict) and prompt_id in runtime_map:
            runtime_map.pop(prompt_id, None)
            store_prompts.jti_runtime_settings_by_prompt = runtime_map
            changed = True

        persona_map = getattr(store_prompts, "jti_persona_by_prompt", None)
        if isinstance(persona_map, dict) and prompt_id in persona_map:
            persona_map.pop(prompt_id, None)
            store_prompts.jti_persona_by_prompt = persona_map
            changed = True

        if changed:
            deps.prompt_manager._save_store_prompts(store_prompts)

        return {"message": "人物設定已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/active")
def set_active_jti_prompt(
    request: SetActivePromptRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    """設定啟用的人物設定，切換後清除所有 chat session

    prompt_id = None → 回到使用預設
    """
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)

    try:
        if request.prompt_id and request.prompt_id != SYSTEM_DEFAULT_ID:
            deps.prompt_manager.set_active_prompt(store_name, request.prompt_id)
        else:
            deps.prompt_manager.clear_active_prompt(store_name)

        main_agent.remove_all_sessions()

        return {
            "message": "已設定啟用的人物設定",
            "prompt_id": request.prompt_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/active")
def get_active_jti_prompt(language: str = "zh", auth: dict = Depends(verify_auth)):
    """取得當前啟用的人物設定"""
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
    """取得 JTI runtime 設定（分段回覆規則/歡迎文字/字數限制）"""
    store_name = _get_store_name_for_language(language)
    runtime_prompt_id = _validate_and_resolve_prompt_id(prompt_id, store_name)
    settings = load_runtime_settings_from_prompt_manager(
        deps.prompt_manager,
        runtime_prompt_id,
        store_name=store_name,
    )
    return {
        "prompt_id": runtime_prompt_id,
        "settings": settings.model_dump(),
    }


@router.post("/runtime-settings")
def update_runtime_settings(
    request: UpdateRuntimeSettingsRequest,
    language: str = "zh",
    auth: dict = Depends(verify_auth),
):
    """更新 JTI runtime 設定，更新後清除 chat sessions。"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    store_name = _get_store_name_for_language(language)
    runtime_prompt_id = _validate_and_resolve_prompt_id(request.prompt_id, store_name)
    if runtime_prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(
            status_code=403,
            detail="預設人物設定的回覆規則為唯讀，請先建立副本並啟用後再編輯。",
        )
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

    return {
        "message": "已更新回覆規則設定",
        "prompt_id": runtime_prompt_id,
        "settings": updated.model_dump(),
    }
