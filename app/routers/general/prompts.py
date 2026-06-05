"""
Prompt Management API Endpoints

主頁的 Prompt 管理：
- DB 只存使用者自訂的 prompts（使用 prompts[] 陣列）。
- 沒有自訂 prompt 時列表為空，後端 chat pipeline 用 code 裡的 PERSONA fallback。
- 此模組「不」讀取 JTI/HCIoT 抽出去的 persona/runtime 設定（`jti_profiles_by_prompt`、
  `hciot_persona_by_prompt` 等），保持兩邊獨立。
"""

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_authenticated
from app.routers.general.stores import resolve_store_config
import app.deps as deps

SYSTEM_DEFAULT_PROMPT_ID = "system_default"

router = APIRouter(
    prefix="/api/stores",
    tags=["Prompt Management"],
    dependencies=[Depends(verify_authenticated)],
)


class CreatePromptRequest(BaseModel):
    name: str
    content: str
    content_en: Optional[str] = None
    response_rule_sections: Optional[Dict[str, Dict[str, str]]] = None
    welcome: Optional[Dict[str, Dict[str, str]]] = None
    max_response_chars: Optional[int] = None


class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    content_en: Optional[str] = None
    response_rule_sections: Optional[Dict[str, Dict[str, str]]] = None
    welcome: Optional[Dict[str, Dict[str, str]]] = None
    max_response_chars: Optional[int] = None


class SetActivePromptRequest(BaseModel):
    prompt_id: Optional[str] = None


_APP_PROMPT_MODULES = {"jti", "hciot"}


def _app_prompt_module(app: str):
    if app == "jti":
        from app.services.jti import agent_prompts
    elif app == "hciot":
        from app.services.hciot import agent_prompts
    else:
        from app.services.general import agent_prompts
    return agent_prompts


def _assembled_app_prompt(app_prompts, language: str) -> str:
    """The app's DEFAULT prompt fully assembled into one string (the same text
    the agent actually runs), so an admin can copy it wholesale rather than
    reassembling the persona + rule-section pieces by hand."""
    persona = app_prompts.PERSONA.get(language, app_prompts.PERSONA["zh"])
    sections = app_prompts.DEFAULT_RESPONSE_RULE_SECTIONS.get(
        language, app_prompts.DEFAULT_RESPONSE_RULE_SECTIONS["zh"]
    )
    # jti/hciot name the char-limit kwarg differently (max_response_chars vs
    # limit) but both default to their own DEFAULT_MAX_RESPONSE_CHARS, so omit it.
    return app_prompts.build_system_instruction(
        persona=persona,
        language=language,
        response_rule_sections=sections,
    )


def _system_default_prompt_item(store_name: str) -> dict:
    """A read-only "系統預設" entry for the prompt list.

    For a managed app store (__jti__/__hciot__) it carries that app's fully
    assembled default prompt; for any other (general/dynamic) store it carries
    the generic General default. This lets the prompt panel show — and let the
    admin copy or keep active — the built-in default alongside custom prompts,
    without persisting anything. Reads module constants only; mutates nothing.
    """
    config = resolve_store_config(store_name)
    managed_app = getattr(config, "managed_app", None) if config else None
    is_managed = bool(config and config.managed_language and managed_app in _APP_PROMPT_MODULES)
    src = _app_prompt_module(managed_app if is_managed else "general")

    name = "系統預設"
    if is_managed:
        name = f"系統預設（{'JTI' if managed_app == 'jti' else 'HCIoT'}）"

    return {
        "id": SYSTEM_DEFAULT_PROMPT_ID,
        "name": name,
        "content": src.PERSONA.get("zh", ""),
        "content_en": src.PERSONA.get("en"),
        "response_rule_sections": src.DEFAULT_RESPONSE_RULE_SECTIONS,
        "max_response_chars": src.DEFAULT_MAX_RESPONSE_CHARS or None,
        # Fully-assembled prompt text, so "copy to custom" can drop the whole
        # thing into the persona/content field instead of split sections.
        "assembled": {
            "zh": _assembled_app_prompt(src, "zh"),
            "en": _assembled_app_prompt(src, "en"),
        },
        "is_default": True,
        "readonly": True,
        "is_active": False,
    }


@router.get("/app-default-prompts/{app}")
def get_app_default_prompt(app: str):
    """Return a managed app's built-in DEFAULT prompt, fully assembled.

    Read-only convenience so the prompt editor can show the complete JTI/HCIoT
    default text (per language) to copy wholesale into another store's custom
    prompt. Reads only module-level constants — never mutates the app modules —
    and only jti/hciot have a built-in default (others 404).
    """
    normalized = (app or "").strip().lower()
    if normalized not in _APP_PROMPT_MODULES:
        raise HTTPException(status_code=404, detail="No built-in default prompt for this app")

    app_prompts = _app_prompt_module(normalized)

    return {
        "app": normalized,
        "is_default": True,
        "readonly": True,
        # Fully-assembled prompt text per language — copy/paste ready.
        "assembled": {
            "zh": _assembled_app_prompt(app_prompts, "zh"),
            "en": _assembled_app_prompt(app_prompts, "en"),
        },
        "max_response_chars": app_prompts.DEFAULT_MAX_RESPONSE_CHARS,
    }


@router.get("/{store_name:path}/prompts")
def list_store_prompts(store_name: str):
    """列出 Store 的所有 Prompts。

    只回傳使用者自訂的 prompts。沒建任何 prompt 時列表為空。
    """
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    custom_prompts = [p.model_dump() for p in deps.prompt_manager.list_prompts(store_name)]
    active_prompt = deps.prompt_manager.get_active_prompt(store_name)
    active_prompt_id = active_prompt.id if active_prompt else None

    for p in custom_prompts:
        p["is_default"] = False
        p["readonly"] = False
        p["is_active"] = p["id"] == active_prompt_id

    # Prepend the read-only built-in default so the panel can show it, let the
    # admin copy it, or keep it active (active when no custom prompt is chosen).
    default_item = _system_default_prompt_item(store_name)
    default_item["is_active"] = active_prompt_id is None

    return {
        "prompts": [default_item, *custom_prompts],
        "active_prompt_id": active_prompt_id,
        "max_prompts": deps.prompt_manager.MAX_PROMPTS_PER_STORE,
    }


@router.post("/{store_name:path}/prompts")
def create_store_prompt(store_name: str, request: CreatePromptRequest):
    """建立新的 Prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        prompt = deps.prompt_manager.create_prompt(
            store_name=store_name,
            name=request.name,
            content=request.content,
            content_en=request.content_en,
            response_rule_sections=request.response_rule_sections,
            welcome=request.welcome,
            max_response_chars=request.max_response_chars,
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{store_name:path}/prompts/{prompt_id}")
def get_store_prompt(store_name: str, prompt_id: str):
    """取得特定 Prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompt = deps.prompt_manager.get_prompt(store_name, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt 不存在")

    return prompt.model_dump()


@router.put("/{store_name:path}/prompts/{prompt_id}")
def update_store_prompt(
    store_name: str,
    prompt_id: str,
    request: UpdatePromptRequest,
):
    """更新 Prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        prompt = deps.prompt_manager.update_prompt(
            store_name=store_name,
            prompt_id=prompt_id,
            name=request.name,
            content=request.content,
            content_en=request.content_en,
            response_rule_sections=request.response_rule_sections,
            welcome=request.welcome,
            max_response_chars=request.max_response_chars,
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{store_name:path}/prompts/{prompt_id}")
def delete_store_prompt(store_name: str, prompt_id: str):
    """刪除 Prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        deps.prompt_manager.delete_prompt(store_name, prompt_id)
        return {"message": "Prompt 已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{store_name:path}/prompts/active")
def set_active_store_prompt(store_name: str, request: SetActivePromptRequest):
    """設定啟用的 Prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        if request.prompt_id:
            deps.prompt_manager.set_active_prompt(store_name, request.prompt_id)
            return {"message": "已設定啟用的 Prompt", "prompt_id": request.prompt_id}
        deps.prompt_manager.clear_active_prompt(store_name)
        return {"message": "已清除啟用的 Prompt", "prompt_id": None}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{store_name:path}/prompts/active")
def get_active_store_prompt(store_name: str):
    """取得當前啟用的 Prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompt = deps.prompt_manager.get_active_prompt(store_name)
    if not prompt:
        return {"message": "尚未設定啟用的 Prompt", "prompt": None}

    return {"prompt": prompt.model_dump()}
