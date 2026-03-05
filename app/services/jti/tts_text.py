"""Helpers for preparing TTS text."""

from __future__ import annotations

from typing import Optional

try:
    from opencc import OpenCC  # type: ignore
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    OpenCC = None  # type: ignore

_T2S_CONVERTER = OpenCC("t2s") if OpenCC else None


def to_tts_text(text: Optional[str], language: str) -> Optional[str]:
    """
    Prepare text for TTS.

    - Non-Chinese languages: keep original text
    - Chinese: convert Traditional Chinese to Simplified Chinese for TTS engines
    """
    if not text:
        return text

    normalized_language = (
        "en"
        if isinstance(language, str) and language.strip().lower().startswith("en")
        else "zh"
    )
    if normalized_language != "zh":
        return text

    if not _T2S_CONVERTER:
        return text

    try:
        return _T2S_CONVERTER.convert(text)
    except Exception:
        return text

