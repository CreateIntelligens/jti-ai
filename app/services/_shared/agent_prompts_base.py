"""Shared base for app-specific agent prompts (persona, rules, welcome, system instruction)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Optional

from app.services.safety_prompts import SENSITIVE_HANDLING, wrap_with_safety

SUPPORTED_LANGUAGES = ("zh", "en")


@dataclass(frozen=True)
class RuleHeaders:
    role: str
    scope: str
    rules: str
    kb: str
    sensitive: str


DEFAULT_RULE_HEADERS_ZH = RuleHeaders(
    role="## 你的角色",
    scope="## 範圍限制",
    rules="## 回應規則",
    kb="## 知識庫使用規則",
    sensitive="## 敏感議題處理",
)

DEFAULT_RULE_HEADERS_EN = RuleHeaders(
    role="## Your Role",
    scope="## Scope Restriction",
    rules="## Response Rules",
    kb="## Knowledge Base Usage",
    sensitive="## Sensitive Topics",
)


@dataclass
class AgentPrompts:
    """Container for an app's editable prompt assets and prompt-building behavior.

    Subclass to customize length-rule wording or rule-section headers; override
    `length_rule()` / `headers_for()` if needed.

    Toggles `include_scope`, `include_sensitive`, and `include_safety_wrap` let
    minimal variants (e.g. internal-facing knowledge bases) skip safety wrapping
    and sensitive-topic blocks while still sharing the assembly skeleton.
    """

    persona: Dict[str, str]
    response_rule_sections: Dict[str, Dict[str, str]]
    welcome_text: Dict[str, Dict[str, str]]
    session_state_templates: Dict[str, str]
    default_max_response_chars: int
    headers_zh: RuleHeaders = field(default_factory=lambda: DEFAULT_RULE_HEADERS_ZH)
    headers_en: RuleHeaders = field(default_factory=lambda: DEFAULT_RULE_HEADERS_EN)
    include_scope: bool = True
    include_sensitive: bool = True
    include_safety_wrap: bool = True
    omit_length_when_unlimited: bool = False

    def get_default_response_rule_sections(self) -> Dict[str, Dict[str, str]]:
        return deepcopy(self.response_rule_sections)

    def get_default_persona(self) -> Dict[str, str]:
        return deepcopy(self.persona)

    def get_default_welcome(self) -> Dict[str, Dict[str, str]]:
        return deepcopy(self.welcome_text)

    def headers_for(self, language: str) -> RuleHeaders:
        return self.headers_en if language == "en" else self.headers_zh

    def length_rule(self, language: str, max_response_chars: int) -> str:
        is_en = language == "en"
        if max_response_chars and max_response_chars > 0:
            return (
                f"- Length: keep each response within {max_response_chars} characters"
                if is_en
                else f"- 字數：每次回覆不超過{max_response_chars}字（必要時更短）"
            )
        if self.omit_length_when_unlimited:
            return ""
        return (
            "- Length: no strict character limit"
            if is_en
            else "- 字數：不限制（可依情境自然回覆）"
        )

    def compose_response_rules(
        self,
        language: str,
        sections: Dict[str, str],
        max_response_chars: int,
    ) -> str:
        normalized_lang = "en" if language == "en" else "zh"
        headers = self.headers_for(normalized_lang)
        length_rule = self.length_rule(normalized_lang, max_response_chars)

        parts: list[str] = [
            f"{headers.role}\n\n{sections.get('role_scope', '')}",
        ]
        if self.include_scope:
            parts.append(f"{headers.scope}\n\n{sections.get('scope_limits', '')}")

        response_style = sections.get("response_style", "")
        rules_body = response_style + (f"\n{length_rule}" if length_rule else "")
        parts.append(f"{headers.rules}\n\n{rules_body}")

        parts.append(f"{headers.kb}\n\n{sections.get('knowledge_rules', '')}")

        if self.include_sensitive:
            sensitive_block = SENSITIVE_HANDLING[normalized_lang]
            parts.append(f"{headers.sensitive}\n\n{sensitive_block}")

        return "\n\n".join(parts)

    def build_system_instruction(
        self,
        persona: str,
        language: str,
        response_rule_sections: Optional[Dict[str, str]] = None,
        max_response_chars: Optional[int] = None,
    ) -> str:
        normalized_lang = "en" if language == "en" else "zh"
        sections = response_rule_sections or self.response_rule_sections.get(
            normalized_lang, self.response_rule_sections["zh"]
        )
        limit = (
            max_response_chars
            if max_response_chars is not None
            else self.default_max_response_chars
        )
        rules = self.compose_response_rules(normalized_lang, sections, limit)
        prefixed_persona = (
            wrap_with_safety(persona, normalized_lang)
            if self.include_safety_wrap
            else persona
        )
        return f"{prefixed_persona}\n\n{rules}"
