"""模型清單端點 — 動態回傳可用的 Gemini 模型。"""

from dataclasses import asdict

from fastapi import APIRouter, Request

from app.models_config import DEFAULT_USER_MODEL
from app.services.gemini_clients import get_client_for_api_key, get_default_client
from app.services.model_discovery import get_available_models

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models(request: Request):
    """回傳目前可用的 Gemini 模型清單及預設模型名稱。"""
    api_key = request.headers.get("x-gemini-api-key")
    client = get_client_for_api_key(api_key) if api_key else get_default_client()
    models = get_available_models(client)

    return {
        "models": [asdict(model) for model in models],
        "default_model": DEFAULT_USER_MODEL,
    }
