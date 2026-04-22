"""JTI response text assembly helpers.

Centralizes quiz display text and TTS payload generation so JTI routes and
services share one formatting path.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.jti.tts import to_jti_tts_text

QUIZ_OPENING = {
    "zh": "簡單四個問題，幫你找到命定保護殼，如果中途想離開，請輸入「中斷」，即可回到問答模式，讓我們開始測驗吧！",
    "en": "Just four questions to find your perfect phone case! If you want to leave midway, type pause to return to chat. Let's begin!",
}


def label_option_texts(options: list[dict[str, Any]]) -> list[str]:
    """Return labelled option strings, e.g. ['A. 簡約', 'B. 可愛']."""
    labels = "ABCDE"
    return [
        f"{labels[i]}. {option.get('text', '')}"
        for i, option in enumerate(options)
        if i < len(labels)
    ]


def format_option_texts(options: list[dict[str, Any]]) -> str:
    """Format options as a newline-separated string for display in messages."""
    return "\n".join(label_option_texts(options))


def extract_option_texts(question: Optional[dict[str, Any]]) -> Optional[list[str]]:
    """Extract labelled option list (e.g. ['A. 簡約', 'B. 可愛']) from a question."""
    if not isinstance(question, dict):
        return None

    options = question.get("options", [])
    if not options:
        return None
    return label_option_texts(options)


def build_quiz_question_text(
    question: Optional[dict[str, Any]],
    question_number: int,
    language: str,
) -> str:
    """Build quiz-mode text for a question without options."""
    text = question.get("text", "") if isinstance(question, dict) else ""
    if language == "en":
        return f"Question {question_number}: {text}"
    return f"第{question_number}題：{text}"


def build_jti_response_fields(
    message: str,
    language: str,
    *,
    tts_source: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Build the shared message/TTS field pair for a JTI response."""
    raw_tts = message if tts_source is None else tts_source
    return {
        "message": message,
        "tts_text": to_jti_tts_text(raw_tts, language),
    }


def build_jti_quiz_question_fields(
    question: Optional[dict[str, Any]],
    question_number: int,
    language: str,
    *,
    prefix: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Build message/TTS fields for a quiz question response."""
    question_text = build_quiz_question_text(question, question_number, language)
    options = question.get("options", []) if isinstance(question, dict) else []
    options_text = format_option_texts(options)
    message_body = f"{question_text}\n{options_text}"
    message = f"{prefix}\n\n{message_body}" if prefix else message_body
    tts_source = f"{prefix} {question_text}" if prefix else question_text
    return build_jti_response_fields(message, language, tts_source=tts_source)
