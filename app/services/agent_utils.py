"""
Agent 共用工具函式

提供 JTI / HCIoT main_agent 共用的語言正規化、Gemini 回應文字擷取等 helper。
"""

import re
from google.genai import types


def normalize_language(language: str) -> str:
    """將語言代碼正規化為 'en' 或 'zh'。"""
    if isinstance(language, str) and language.strip().lower().startswith("en"):
        return "en"
    return "zh"


def extract_response_text(response) -> str:
    """從 Gemini GenerateContentResponse 擷取所有文字 part 並串接。"""
    if not response.candidates or not response.candidates[0].content.parts:
        return ""
    return "".join(
        part.text
        for part in response.candidates[0].content.parts
        if hasattr(part, "text") and part.text
    )


def strip_citations(text: str) -> str:
    """移除 Gemini File Search 的 [cite:...] 標記。"""
    return re.sub(r"\s*\[cite:\s*[^\]]*\]", "", text).strip()


def build_chat_history(chat_history: list) -> list[types.Content]:
    """將 MongoDB 格式的 chat_history 轉換為 Gemini SDK Content 物件列表。"""
    contents = []
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])],
            )
        )
    return contents
