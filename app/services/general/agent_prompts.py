"""
General Knowledge Base Agent Prompts.

Simpler than JTI/HCIoT (no quiz/TTS/safety filter; persona comes from
prompt_manager's active prompt), 但仍透過共用 `AgentPrompts` base 組裝，
只是關閉了 safety wrap、scope 段與敏感議題段。
"""

from __future__ import annotations

from typing import Dict, Optional

from app.services._shared.agent_prompts_base import AgentPrompts, RuleHeaders

DEFAULT_MAX_RESPONSE_CHARS = 0  # No character limit for general KB chat

PERSONA: Dict[str, str] = {
    "zh": """你是一個知識庫問答助手。

- 任務：根據知識庫提供的資料回答使用者的問題
- 說話風格：清楚、有條理、不囉嗦
- 原則：優先使用知識庫資料，沒有資料時誠實說明""",
    "en": """You are a knowledge base Q&A assistant.

- Task: answer user questions based on the knowledge base content
- Tone: clear, organized, concise
- Principle: prioritize knowledge base content; be honest when information is unavailable""",
}

DEFAULT_RESPONSE_RULE_SECTIONS: Dict[str, Dict[str, str]] = {
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

WELCOME_TEXT: Dict[str, Dict[str, str]] = {
    "zh": {
        "title": "歡迎使用通用知識庫助手",
        "description": "依據你選擇的知識庫內容回答問題。",
    },
    "en": {
        "title": "Welcome to the General Knowledge Assistant",
        "description": "Ask questions grounded in the knowledge base you selected.",
    },
}

SESSION_STATE_TEMPLATES: Dict[str, str] = {
    "zh": """<內部狀態資訊 - 不要在回應中提及>
目前模式: 知識庫問答
現在時間: {now}
</內部狀態資訊>""",
    "en": """<Internal State Info - Do not mention in response>
Current Mode: Knowledge base Q&A
Current time: {now}
</Internal State Info>""",
}

# General 不顯示「範圍限制」與「敏感議題」段，header 只用到 role/rules/kb。
_GENERAL_HEADERS_ZH = RuleHeaders(
    role="## 你的角色",
    scope="",
    rules="## 回應規則",
    kb="## 知識庫使用規則",
    sensitive="",
)

_GENERAL_HEADERS_EN = RuleHeaders(
    role="## Your Role",
    scope="",
    rules="## Response Rules",
    kb="## Knowledge Base Usage",
    sensitive="",
)


class _GeneralAgentPrompts(AgentPrompts):
    """General KB 使用較簡潔的字數措辭（不加「（必要時更短）」）。"""

    def length_rule(self, language: str, max_response_chars: int) -> str:
        is_en = language == "en"
        if max_response_chars and max_response_chars > 0:
            return (
                f"- Length: keep each response within {max_response_chars} characters"
                if is_en
                else f"- 字數：每次回覆不超過{max_response_chars}字"
            )
        return ""


prompts = _GeneralAgentPrompts(
    persona=PERSONA,
    response_rule_sections=DEFAULT_RESPONSE_RULE_SECTIONS,
    welcome_text=WELCOME_TEXT,
    session_state_templates=SESSION_STATE_TEMPLATES,
    default_max_response_chars=DEFAULT_MAX_RESPONSE_CHARS,
    headers_zh=_GENERAL_HEADERS_ZH,
    headers_en=_GENERAL_HEADERS_EN,
    include_scope=False,
    include_sensitive=False,
    include_safety_wrap=False,
    omit_length_when_unlimited=True,
)


def build_system_instruction(
    persona: str,
    language: str,
    response_rule_sections: Optional[Dict[str, str]] = None,
    max_response_chars: int = DEFAULT_MAX_RESPONSE_CHARS,
) -> str:
    """Build system instruction for general KB chat."""
    return prompts.build_system_instruction(
        persona=persona,
        language=language,
        response_rule_sections=response_rule_sections,
        max_response_chars=max_response_chars,
    )
