"""
General Knowledge Base Agent Prompts

Simpler than JTI/HCIoT:
- No quiz, no TTS, no safety filter (general KB is internal-facing)
- Persona is read from prompt_manager's active prompt content (per-store)
- Session state is minimal (just mode + timestamp)
"""

from __future__ import annotations

from typing import Dict, Optional


DEFAULT_MAX_RESPONSE_CHARS = 0  # No character limit for general KB chat

# ===== Default persona (used when no prompt_manager persona is configured) =====
PERSONA = {
    "zh": """你是一個知識庫問答助手。

- 任務：根據知識庫提供的資料回答使用者的問題
- 說話風格：清楚、有條理、不囉嗦
- 原則：優先使用知識庫資料，沒有資料時誠實說明""",
    "en": """You are a knowledge base Q&A assistant.

- Task: answer user questions based on the knowledge base content
- Tone: clear, organized, concise
- Principle: prioritize knowledge base content; be honest when information is unavailable""",
}

# ===== Response rule sections =====
DEFAULT_RESPONSE_RULE_SECTIONS = {
    "zh": {
        "role_scope": "1. 根據知識庫內容回答使用者問題\n2. 將知識庫查到的資訊整理成容易理解的回覆",
        "scope_limits": "- 回答時以知識庫資料為主\n- 如果問題與知識庫無關，可以禮貌地說明",
        "response_style": "- 使用繁體中文回覆\n- 格式清楚自然即可",
        "knowledge_rules": "- 優先依據知識庫查到的內容回答\n- 知識庫沒有提到的資訊，請直接說明「資料中沒有提到」",
    },
    "en": {
        "role_scope": "1. Answer user questions based on knowledge base content\n2. Organize retrieved information into clear responses",
        "scope_limits": "- Prioritize knowledge base content\n- If the question is unrelated, politely explain",
        "response_style": "- Respond in English\n- Keep formatting clean and natural",
        "knowledge_rules": "- Use knowledge base content as the primary source\n- If the information is not in the KB, say so clearly",
    },
}

# ===== Session state template (minimal for general KB) =====
SESSION_STATE_TEMPLATES = {
    "zh": """<內部狀態資訊 - 不要在回應中提及>
目前模式: 知識庫問答
現在時間: {now}
</內部狀態資訊>""",
    "en": """<Internal State Info - Do not mention in response>
Current Mode: Knowledge base Q&A
Current time: {now}
</Internal State Info>""",
}


def build_system_instruction(
    persona: str,
    language: str,
    response_rule_sections: Optional[Dict[str, str]] = None,
    max_response_chars: int = DEFAULT_MAX_RESPONSE_CHARS,
) -> str:
    """Build system instruction for general KB chat.

    Simpler than JTI/HCIoT: no safety wrapper, no sensitive topic handling.
    """
    normalized_lang = "en" if language == "en" else "zh"
    sections = response_rule_sections or DEFAULT_RESPONSE_RULE_SECTIONS[normalized_lang]

    is_en = normalized_lang == "en"
    headers = {
        "role": "## Your Role" if is_en else "## 你的角色",
        "rules": "## Response Rules" if is_en else "## 回應規則",
        "kb": "## Knowledge Base Usage" if is_en else "## 知識庫使用規則",
    }

    length_section = ""
    if max_response_chars > 0:
        length_rule = (
            f"- Length: keep each response within {max_response_chars} characters"
            if is_en else
            f"- 字數：每次回覆不超過{max_response_chars}字"
        )
        length_section = f"\n{length_rule}"

    rules = f"""{headers['role']}

{sections.get('role_scope', '')}

{headers['rules']}

{sections.get('response_style', '')}{length_section}

{headers['kb']}

{sections.get('knowledge_rules', '')}"""

    return f"{persona}\n\n{rules}"
