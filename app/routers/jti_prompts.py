"""
JTI Prompt Management API Endpoints

JTI 專用的提示詞管理。
預設 prompt 從 agent_prompts.py 讀取（地端唯讀，不存 MongoDB）。
自訂 prompt 最多 3 個，存在 MongoDB。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import verify_auth
from app.services.jti.main_agent import main_agent
from app.services.jti.agent_prompts import SYSTEM_INSTRUCTIONS
import app.deps as deps

router = APIRouter(prefix="/api/jti/prompts", tags=["JTI Prompt Management"])

JTI_STORE_NAME = "__jti__"
SYSTEM_DEFAULT_ID = "system_default"
MAX_CUSTOM_PROMPTS = 3


class CreatePromptRequest(BaseModel):
    name: str
    content: str


class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None


class SetActivePromptRequest(BaseModel):
    prompt_id: Optional[str] = None


def _get_default_prompt_dict() -> dict:
    """從程式碼取得預設提示詞（唯讀）"""
    return {
        "id": SYSTEM_DEFAULT_ID,
        "name": "預設提示詞",
        "content": SYSTEM_INSTRUCTIONS["zh"],
        "created_at": "",
        "updated_at": "",
        "is_default": True,
        "readonly": True,
    }


@router.get("/")
def list_jti_prompts(auth: dict = Depends(verify_auth)):
    """列出所有 JTI prompts（預設 + 自訂）"""
    # 預設提示詞：從程式碼讀取
    default_prompt = _get_default_prompt_dict()

    # 自訂提示詞：從 MongoDB 讀取
    custom_prompts = []
    active_prompt_id = None

    if deps.prompt_manager:
        mongo_prompts = deps.prompt_manager.list_prompts(JTI_STORE_NAME)
        custom_prompts = [p.model_dump() for p in mongo_prompts]
        store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
        active_prompt_id = store_prompts.active_prompt_id

    # 標記自訂提示詞
    for p in custom_prompts:
        p["is_default"] = False
        p["readonly"] = False

    # 如果沒有任何自訂被啟用，預設視為啟用中
    if not active_prompt_id:
        default_prompt["is_active"] = True
    else:
        default_prompt["is_active"] = False

    for p in custom_prompts:
        p["is_active"] = (p["id"] == active_prompt_id)

    return {
        "prompts": [default_prompt] + custom_prompts,
        "active_prompt_id": active_prompt_id,  # None = 使用預設
        "max_custom_prompts": MAX_CUSTOM_PROMPTS,
    }


@router.post("/")
def create_jti_prompt(request: CreatePromptRequest, auth: dict = Depends(verify_auth)):
    """建立自訂 JTI prompt（最多 3 個自訂）"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompts = deps.prompt_manager.list_prompts(JTI_STORE_NAME)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"自訂提示詞最多 {MAX_CUSTOM_PROMPTS} 個",
        )

    from app.prompts import Prompt

    new_prompt = Prompt(name=request.name, content=request.content)
    store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
    store_prompts.prompts.append(new_prompt)
    deps.prompt_manager._save_store_prompts(store_prompts)

    return new_prompt.model_dump()


@router.post("/clone")
def clone_default_prompt(auth: dict = Depends(verify_auth)):
    """複製預設提示詞為新的自訂提示詞，並自動啟用"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompts = deps.prompt_manager.list_prompts(JTI_STORE_NAME)

    if len(prompts) >= MAX_CUSTOM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"自訂提示詞最多 {MAX_CUSTOM_PROMPTS} 個",
        )

    from app.prompts import Prompt

    clone = Prompt(
        name=f"自訂提示詞 {len(prompts) + 1}",
        content=SYSTEM_INSTRUCTIONS["zh"],
    )

    store_prompts = deps.prompt_manager._load_store_prompts(JTI_STORE_NAME)
    store_prompts.prompts.append(clone)
    store_prompts.active_prompt_id = clone.id  # 自動啟用
    deps.prompt_manager._save_store_prompts(store_prompts)

    # 清除所有 chat session，強制下次對話使用新 prompt
    main_agent.remove_all_sessions()

    return {
        "prompt": clone.model_dump(),
        "message": "已複製預設提示詞並啟用",
    }


@router.put("/{prompt_id}")
def update_jti_prompt(prompt_id: str, request: UpdatePromptRequest, auth: dict = Depends(verify_auth)):
    """更新 JTI prompt（禁止修改預設 prompt）"""
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設提示詞為唯讀，無法修改。請使用「以此為基礎建立副本」功能。")

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
    """刪除 JTI prompt（禁止刪除預設 prompt）"""
    if prompt_id == SYSTEM_DEFAULT_ID:
        raise HTTPException(status_code=403, detail="預設提示詞無法刪除")

    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        deps.prompt_manager.delete_prompt(JTI_STORE_NAME, prompt_id)
        return {"message": "提示詞已刪除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/active")
def set_active_jti_prompt(request: SetActivePromptRequest, auth: dict = Depends(verify_auth)):
    """設定啟用的 JTI prompt，切換後清除所有 chat session

    prompt_id = None → 回到使用預設提示詞
    """
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    try:
        if request.prompt_id and request.prompt_id != SYSTEM_DEFAULT_ID:
            deps.prompt_manager.set_active_prompt(JTI_STORE_NAME, request.prompt_id)
        else:
            # 回到使用預設（清除 active_prompt_id）
            deps.prompt_manager.clear_active_prompt(JTI_STORE_NAME)

        # 清除所有 chat session，強制下次對話重建（使用新 prompt）
        main_agent.remove_all_sessions()

        return {
            "message": "已設定啟用的提示詞",
            "prompt_id": request.prompt_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/active")
def get_active_jti_prompt(auth: dict = Depends(verify_auth)):
    """取得當前啟用的 JTI prompt"""
    if not deps.prompt_manager:
        raise HTTPException(status_code=500, detail="Prompt Manager 未初始化")

    prompt = deps.prompt_manager.get_active_prompt(JTI_STORE_NAME)
    if not prompt:
        # 沒有自訂啟用 → 回傳預設
        return {"prompt": _get_default_prompt_dict(), "is_default": True}

    return {"prompt": prompt.model_dump(), "is_default": False}
