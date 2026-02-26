"""
JTI Persona Management API Endpoints

JTI 專用的人物設定管理。
預設人物設定從 agent_prompts.py 讀取（地端唯讀，不存 MongoDB）。
自訂人物設定最多 3 個，存在 MongoDB。
"""

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

JTI_STORE_NAME = "__jti__"
SYSTEM_DEFAULT_ID = SYSTEM_DEFAULT_PROMPT_ID
MAX_CUSTOM_PROMPTS = 3


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


def _get_default_prompt_dict() -> dict:
    """從程式碼取得預設人物設定（唯讀）"""
    return {
        "id": SYSTEM_DEFAULT_ID,
        "name": "預設人物設定",
        "content": PERSONA["zh"],
        "created_at": "",
        "updated_at": "",
        "is_default": True,
        "readonly": True,
    }


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


def _resolve_runtime_prompt_id(requested_prompt_id: Optional[str]) -> str:
    """決定 runtime 設定要套用到哪個人物設定。"""
    if requested_prompt_id:
        if requested_prompt_id == SYSTEM_DEFAULT_ID:
            return SYSTEM_DEFAULT_ID
        if not deps.prompt_manager:
            raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")
        prompt = deps.prompt_manager.get_prompt(JTI_STORE_NAME, requested_prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="人物設定不存在")
        return requested_prompt_id

    if not deps.prompt_manager:
        return SYSTEM_DEFAULT_ID

    store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
    return store_prompts.active_prompt_id or SYSTEM_DEFAULT_ID


@router.get("/")
def list_jti_prompts(auth: dict = Depends(verify_auth)):
    """列出所有 JTI 人物設定（預設 + 自訂）"""
    default_prompt = _get_default_prompt_dict()

    custom_prompts = []
    active_prompt_id = None

    if deps.prompt_manager:
        mongo_prompts = deps.prompt_manager.list_prompts(JTI_STORE_NAME)
        custom_prompts = [p.model_dump() for p in mongo_prompts]
        store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
        active_prompt_id = store_prompts.active_prompt_id

    for p in custom_prompts:
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
def create_jti_prompt(request: CreatePromptRequest, auth: dict = Depends(verify_auth)):
    """建立自訂人物設定（最多 3 個）"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompts = deps.prompt_manager.list_prompts(JTI_STORE_NAME)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"自訂人物設定最多 {MAX_CUSTOM_PROMPTS} 個",
        )

    from app.prompts import Prompt

    new_prompt = Prompt(name=request.name, content=request.content)
    store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
    store_prompts.prompts.append(new_prompt)
    deps.prompt_manager._save_store_prompts(store_prompts)

    base_runtime = load_runtime_settings_from_prompt_manager(deps.prompt_manager, SYSTEM_DEFAULT_ID)
    save_runtime_settings_to_prompt_manager(
        deps.prompt_manager,
        base_runtime,
        prompt_id=new_prompt.id,
    )

    return new_prompt.model_dump()


@router.post("/clone")
def clone_default_prompt(auth: dict = Depends(verify_auth)):
    """複製預設人物設定為新的自訂人物設定，並自動啟用"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompts = deps.prompt_manager.list_prompts(JTI_STORE_NAME)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"自訂人物設定最多 {MAX_CUSTOM_PROMPTS} 個",
        )

    from app.prompts import Prompt

    clone = Prompt(
        name=f"自訂人物設定 {len(prompts) + 1}",
        content=PERSONA["zh"],
    )

    store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
    store_prompts.prompts.append(clone)
    store_prompts.active_prompt_id = clone.id
    deps.prompt_manager._save_store_prompts(store_prompts)

    base_runtime = load_runtime_settings_from_prompt_manager(deps.prompt_manager, SYSTEM_DEFAULT_ID)
    save_runtime_settings_to_prompt_manager(
        deps.prompt_manager,
        base_runtime,
        prompt_id=clone.id,
    )

    main_agent.remove_all_sessions()

    return {
        "prompt": clone.model_dump(),
        "message": "已複製預設人物設定並啟用",
    }


@router.put("/{prompt_id}")
def update_jti_prompt(prompt_id: str, request: UpdatePromptRequest, auth: dict = Depends(verify_auth)):
    """更新人物設定（禁止修改預設）"""
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設人物設定為唯讀，無法修改。請使用「以此為基礎建立副本」功能。")

    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        prompt = deps.prompt_manager.update_prompt(
            JTI_STORE_NAME,
            prompt_id,
            name=request.name,
            content=request.content,
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{prompt_id}")
def delete_jti_prompt(prompt_id: str, auth: dict = Depends(verify_auth)):
    """刪除人物設定（禁止刪除預設）"""
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設人物設定無法刪除")

    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        deps.prompt_manager.delete_prompt(JTI_STORE_NAME, prompt_id)

        store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
        runtime_map = getattr(store_prompts, "jti_runtime_settings_by_prompt", None)
        if isinstance(runtime_map, dict) and prompt_id in runtime_map:
            runtime_map.pop(prompt_id, None)
            store_prompts.jti_runtime_settings_by_prompt = runtime_map
            deps.prompt_manager._save_store_prompts(store_prompts)

        return {"message": "人物設定已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/active")
def set_active_jti_prompt(request: SetActivePromptRequest, auth: dict = Depends(verify_auth)):
    """設定啟用的人物設定，切換後清除所有 chat session

    prompt_id = None → 回到使用預設
    """
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        if request.prompt_id and request.prompt_id != SYSTEM_DEFAULT_ID:
            deps.prompt_manager.set_active_prompt(JTI_STORE_NAME, request.prompt_id)
        else:
            deps.prompt_manager.clear_active_prompt(JTI_STORE_NAME)

        main_agent.remove_all_sessions()

        return {
            "message": "已設定啟用的人物設定",
            "prompt_id": request.prompt_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/active")
def get_active_jti_prompt(auth: dict = Depends(verify_auth)):
    """取得當前啟用的人物設定"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompt = deps.prompt_manager.get_active_prompt(JTI_STORE_NAME)
    if not prompt:
        return {"prompt": _get_default_prompt_dict(), "is_default": True}

    return {"prompt": prompt.model_dump(), "is_default": False}


@router.get("/runtime-settings")
def get_runtime_settings(prompt_id: Optional[str] = None, auth: dict = Depends(verify_auth)):
    """取得 JTI runtime 設定（分段回覆規則/歡迎文字/字數限制）"""
    runtime_prompt_id = _resolve_runtime_prompt_id(prompt_id)
    settings = load_runtime_settings_from_prompt_manager(deps.prompt_manager, runtime_prompt_id)
    return {
        "prompt_id": runtime_prompt_id,
        "settings": settings.model_dump(),
    }


@router.post("/runtime-settings")
def update_runtime_settings(request: UpdateRuntimeSettingsRequest, auth: dict = Depends(verify_auth)):
    """更新 JTI runtime 設定，更新後清除 chat sessions。"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    runtime_prompt_id = _resolve_runtime_prompt_id(request.prompt_id)
    if runtime_prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(
            status_code=403,
            detail="預設人物設定的回覆規則為唯讀，請先建立副本並啟用後再編輯。",
        )
    current = load_runtime_settings_from_prompt_manager(deps.prompt_manager, runtime_prompt_id)
    updated = _merge_runtime_settings(current, request)
    save_runtime_settings_to_prompt_manager(
        deps.prompt_manager,
        updated,
        prompt_id=runtime_prompt_id,
    )
    main_agent.remove_all_sessions()

    return {
        "message": "已更新回覆規則設定",
        "prompt_id": runtime_prompt_id,
        "settings": updated.model_dump(),
    }
