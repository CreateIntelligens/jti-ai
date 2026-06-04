"""
Agent 共用工具函式

提供 JTI / HCIoT main_agent 共用的語言正規化、Gemini 回應文字擷取等 helper。
"""

import re
from google.genai import types

CORE_MARKER_PATTERN = re.compile(r"\[CORE:\s*([^\]]+?)\]", flags=re.IGNORECASE)


def build_search_knowledge_decl(
    domain_description: str,
    queries_description: str,
) -> types.FunctionDeclaration:
    """Build a `search_knowledge` FunctionDeclaration with domain-specific descriptions."""
    return types.FunctionDeclaration(
        name="search_knowledge",
        description=domain_description,
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "queries": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description=queries_description,
                ),
            },
            required=["queries"],
        ),
    )


def normalize_language(language: str | None) -> str:
    """將語言代碼正規化為 'en' 或 'zh'。"""
    if isinstance(language, str) and language.strip().lower().startswith("en"):
        return "en"
    return "zh"


def extract_response_text(response) -> str:
    """從 Gemini GenerateContentResponse 擷取所有文字 part 並串接。"""
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(
        part.text
        for part in parts
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


# 餵給模型的歷史滑動視窗上限（則數，非輪數）。
# 客戶情境本就不需長對話，此上限純為防呆：避免惡意狂灌訊息把 token 撐爆 / 拖慢回應。
# MongoDB 仍儲存完整歷史，這裡只限制「每次請求帶給 Gemini」的筆數。
# 20 輪來回 = 40 則。
MAX_HISTORY_MESSAGES = 40


def _chat_history_window(chat_history: list) -> list:
    windowed = chat_history[-MAX_HISTORY_MESSAGES:]

    # 對齊角色：history 必須以 user 開頭，否則 SDK 會報錯。
    while windowed and windowed[0]["role"] != "user":
        windowed = windowed[1:]

    return windowed


def _chat_message_to_content(msg: dict) -> types.Content:
    role = "user" if msg["role"] == "user" else "model"
    return types.Content(
        role=role,
        parts=[types.Part.from_text(text=msg["content"])],
    )


def build_chat_history(chat_history: list) -> list[types.Content]:
    """將 MongoDB 格式的 chat_history 轉換為 Gemini SDK Content 物件列表。

    只保留最近 ``MAX_HISTORY_MESSAGES`` 則作為滑動視窗。取尾後會確保第一筆為
    user 角色（Gemini 要求 history 以 user 開頭），若切到一半開頭是 model 則往後再裁一則。
    """
    return [_chat_message_to_content(msg) for msg in _chat_history_window(chat_history)]
