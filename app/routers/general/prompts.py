"""
Prompt Management API Endpoints

主頁的 Prompt 管理：
- DB 只存使用者自訂的 prompts（使用 prompts[] 陣列）。
- 沒有自訂 prompt 時列表為空，後端 chat pipeline 用 code 裡的 PERSONA fallback。
- 此模組「不」讀取 JTI/HCIoT 抽出去的 persona/runtime 設定（`jti_profiles_by_prompt`、
  `hciot_persona_by_prompt` 等），保持兩邊獨立。
"""

from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import verify_auth, require_admin
import app.deps as deps

router = APIRouter(prefix="/api/stores", tags=["Prompt Management"])


class CreatePromptRequest(BaseModel):
    name: str
    content: str
    response_rule_sections: Optional[Dict[str, Dict[str, str]]] = None
    welcome: Optional[Dict[str, Dict[str, str]]] = None
    max_response_chars: Optional[int] = None


class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    response_rule_sections: Optional[Dict[str, Dict[str, str]]] = None
    welcome: Optional[Dict[str, Dict[str, str]]] = None
    max_response_chars: Optional[int] = None


class SetActivePromptRequest(BaseModel):
    prompt_id: Optional[str] = None


@router.get("/{store_name:path}/prompts")
def list_store_prompts(store_name: str, auth: dict = Depends(verify_auth)):
    """列出 Store 的所有 Prompts（Admin only）。

    只回傳使用者自訂的 prompts。沒建任何 prompt 時列表為空。
    """
    require_admin(auth)
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    custom_prompts = [p.model_dump() for p in deps.prompt_manager.list_prompts(store_name)]
    active_prompt = deps.prompt_manager.get_active_prompt(store_name)
    active_prompt_id = active_prompt.id if active_prompt else None

    for p in custom_prompts:
        p["is_default"] = False
        p["readonly"] = False
        p["is_active"] = p["id"] == active_prompt_id

    return {
        "prompts": custom_prompts,
        "active_prompt_id": active_prompt_id,
        "max_prompts": deps.prompt_manager.MAX_PROMPTS_PER_STORE,
    }


@router.post("/{store_name:path}/prompts")
def create_store_prompt(store_name: str, request: CreatePromptRequest, auth: dict = Depends(verify_auth)):
    """建立新的 Prompt（Admin only）"""
    require_admin(auth)
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        prompt = deps.prompt_manager.create_prompt(
            store_name=store_name,
            name=request.name,
            content=request.content,
            response_rule_sections=request.response_rule_sections,
            welcome=request.welcome,
            max_response_chars=request.max_response_chars,
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{store_name:path}/prompts/{prompt_id}")
def get_store_prompt(store_name: str, prompt_id: str, auth: dict = Depends(verify_auth)):
    """取得特定 Prompt（Admin only）"""
    require_admin(auth)
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompt = deps.prompt_manager.get_prompt(store_name, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt 不存在")

    return prompt.model_dump()


@router.put("/{store_name:path}/prompts/{prompt_id}")
def update_store_prompt(store_name: str, prompt_id: str, request: UpdatePromptRequest, auth: dict = Depends(verify_auth)):
    """更新 Prompt（Admin only）"""
    require_admin(auth)
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        prompt = deps.prompt_manager.update_prompt(
            store_name=store_name,
            prompt_id=prompt_id,
            name=request.name,
            content=request.content,
            response_rule_sections=request.response_rule_sections,
            welcome=request.welcome,
            max_response_chars=request.max_response_chars,
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{store_name:path}/prompts/{prompt_id}")
def delete_store_prompt(store_name: str, prompt_id: str, auth: dict = Depends(verify_auth)):
    """刪除 Prompt（Admin only）"""
    require_admin(auth)
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        deps.prompt_manager.delete_prompt(store_name, prompt_id)
        return {"message": "Prompt 已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{store_name:path}/prompts/active")
def set_active_store_prompt(store_name: str, request: SetActivePromptRequest, auth: dict = Depends(verify_auth)):
    """設定啟用的 Prompt（Admin only）"""
    require_admin(auth)
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
def get_active_store_prompt(store_name: str, auth: dict = Depends(verify_auth)):
    """取得當前啟用的 Prompt（Admin only）"""
    require_admin(auth)
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompt = deps.prompt_manager.get_active_prompt(store_name)
    if not prompt:
        return {"message": "尚未設定啟用的 Prompt", "prompt": None}

    return {"prompt": prompt.model_dump()}
