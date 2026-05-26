"""Centralized Gemini model configuration."""

import os

SUPPORTED_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
)

CHAT_MODEL = "gemini-3.1-flash-lite"

DEFAULT_MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

DEFAULT_RAG_MODEL = os.getenv("GEMINI_MODEL_NAME", CHAT_MODEL)

QUIZ_HELPER_MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")

# Fallback chain: when a model returns 404 "no longer available", try the next.
# Order matters: primary first, then descending capability.
FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)


def fallback_chain(primary: str) -> tuple[str, ...]:
    """Return primary followed by configured fallback models, without duplicates."""
    fallbacks = tuple(model for model in FALLBACK_MODELS if model != primary)
    return (primary,) + fallbacks
