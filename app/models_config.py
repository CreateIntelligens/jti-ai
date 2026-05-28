"""Centralized Gemini model configuration."""

import os

# 統一讀取 GEMINI_MODEL_NAME，預設為已上架的 gemini-3.1-flash-lite
# (原 -preview 版已下架；fallback chain 在失敗時自動切到備用模型)
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")

CHAT_MODEL = GEMINI_MODEL_NAME
DEFAULT_MODEL = GEMINI_MODEL_NAME
DEFAULT_USER_MODEL = GEMINI_MODEL_NAME
DEFAULT_RAG_MODEL = GEMINI_MODEL_NAME
QUIZ_HELPER_MODEL = GEMINI_MODEL_NAME

SUPPORTED_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
)

# Fallback chain: when a model returns 404 "no longer available", try the next.
# Order: primary first, then lighter sibling, then heavier sibling as last resort.
FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)


from typing import Any

def fallback_chain(primary: str, client: Any = None) -> tuple[str, ...]:
    """Return primary followed by configured fallback models, without duplicates.

    If client is provided, dynamically discover available models from API first.
    """
    if client is not None:
        try:
            from app.services.model_discovery import get_available_models
            available = get_available_models(client)
            if available:
                chain = [primary]
                for model in available:
                    name = model.name
                    if name != primary and name not in chain:
                        chain.append(name)
                return tuple(chain)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Dynamic model discovery failed in fallback_chain: %s", e)

    fallbacks = tuple(model for model in FALLBACK_MODELS if model != primary)
    return (primary,) + fallbacks
