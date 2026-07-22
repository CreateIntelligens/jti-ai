"""Centralized Gemini model configuration."""

import logging
import os
from typing import Any

GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-flash-lite-latest")

CHAT_MODEL = GEMINI_MODEL_NAME
DEFAULT_MODEL = GEMINI_MODEL_NAME
DEFAULT_USER_MODEL = GEMINI_MODEL_NAME
DEFAULT_RAG_MODEL = GEMINI_MODEL_NAME
QUIZ_HELPER_MODEL = GEMINI_MODEL_NAME

SUPPORTED_MODELS: tuple[str, ...] = (
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)

FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)


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
                available_names = [model.name for model in available]
                available_name_set = set(available_names)
                for name in FALLBACK_MODELS:
                    if name != primary and name in available_name_set:
                        chain.append(name)
                for model in available:
                    name = model.name
                    if name not in chain:
                        chain.append(name)
                return tuple(chain)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Dynamic model discovery failed in fallback_chain: %s",
                exc,
            )

    fallbacks = tuple(model for model in FALLBACK_MODELS if model != primary)
    return (primary,) + fallbacks
