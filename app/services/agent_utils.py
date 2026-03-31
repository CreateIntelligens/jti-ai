"""
Agent 共用工具函式

提供 JTI / HCIoT main_agent 共用的語言正規化、Gemini 回應文字擷取等 helper。
"""

import re
from google.genai import types

CORE_MARKER_PATTERN = re.compile(r"\[CORE:\s*([^\]]+?)\]", flags=re.IGNORECASE)


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
    """移除模型回覆中的檢索標記，並保留 CORE 內容本身。"""
    text = strip_core_markup(text)
    text = re.sub(r"\s*\[cite:\s*[^\]]*\]", "", text)
    return text.strip()


def strip_core_markup(text: str) -> str:
    """移除 [CORE: ...] 外殼並保留其中內容。"""
    return CORE_MARKER_PATTERN.sub(r"\1", text)


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
