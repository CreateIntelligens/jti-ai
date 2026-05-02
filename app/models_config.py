"""Centralized Gemini model configuration."""

import os

SUPPORTED_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite-preview",
)

CHAT_MODEL = "gemini-3.1-flash-lite-preview"

DEFAULT_MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

DEFAULT_RAG_MODEL = os.getenv("GEMINI_MODEL_NAME", CHAT_MODEL)

QUIZ_HELPER_MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
