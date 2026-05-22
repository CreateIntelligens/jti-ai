"""Centralized Gemini model configuration."""

import os

# 統一讀取 GEMINI_MODEL_NAME，且預設值皆為 3.1 (gemini-3.1-flash-lite-preview)
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite-preview")

CHAT_MODEL = GEMINI_MODEL_NAME
DEFAULT_MODEL = GEMINI_MODEL_NAME
DEFAULT_USER_MODEL = GEMINI_MODEL_NAME
DEFAULT_RAG_MODEL = GEMINI_MODEL_NAME
QUIZ_HELPER_MODEL = GEMINI_MODEL_NAME
