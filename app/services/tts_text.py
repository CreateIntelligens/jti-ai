"""Generic helpers for preparing zh TTS text."""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

try:
    from opencc import OpenCC  # type: ignore
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    OpenCC = None  # type: ignore

try:
    import httpx as _httpx  # type: ignore
except Exception:  # pragma: no cover
    _httpx = None  # type: ignore

from app.services.agent_utils import normalize_language
from app.services.safety_numbers import TTS_SPOKEN_SHORT_CODES

logger = logging.getLogger(__name__)

_T2S_CONVERTER = OpenCC("t2s") if OpenCC else None

# Set NORMALIZE_API_URL to enable the normalize API for digit conversion + OpenCC.
# Leave empty (or unset) to use the local regex fallback.
_NORMALIZE_API_URL = os.getenv("NORMALIZE_API_URL", "").strip()

_DIGIT_MAP = "零一二三四五六七八九"
_UNITS = ["", "十", "百", "千"]
_BIG_UNITS = ["", "萬", "億"]
_DIGIT_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_HOTLINE_PATTERN = re.compile(
    rf"(?<!\d)({'|'.join(sorted(TTS_SPOKEN_SHORT_CODES, key=len, reverse=True))})(?!\d)"
)
_LIANG_PATTERN = re.compile(r"二([百千萬億])")
_PHONE_PATTERN = re.compile(r"\(?\d+\)?[\-\s]?\d[\d\-\s]{4,}\d")
_YEAR_PATTERN = re.compile(r"(\d{4})年")
_MIN_DIGITS = 3


def _to_simplified_chinese(text: str) -> str:
    if _T2S_CONVERTER:
        try:
            return _T2S_CONVERTER.convert(text)
        except Exception:
            pass
    return text


def _normalize_via_api(text: str) -> Optional[str]:
    """Call the normalize API and return the simplified (digits+opencc) result.

    Returns None if NORMALIZE_API_URL is not set, the API is unreachable,
    or the response is unexpected.
    """
    if not _NORMALIZE_API_URL or not _httpx:
        return None
    try:
        response = _httpx.post(
            _NORMALIZE_API_URL,
            json={"text": text},
            timeout=5.0,
        )
        response.raise_for_status()
        result = response.json().get("simplified")
        logger.info("normalize API hit: %r -> %r", text[:40], (result or "")[:40])
        return result
    except Exception as exc:
        logger.warning("normalize API failed, falling back to regex: %s", exc)
        return None


def _prepare_with_regex(text: str) -> str:
    """Prepare TTS text using the local regex pipeline."""
    prepared = _replace_hotlines_with_spoken_digits(text)
    prepared = digits_to_chinese(prepared)
    return _to_simplified_chinese(prepared)


def prepare_tts_text(text: Optional[str], language: str) -> Optional[str]:
    if not text or normalize_language(language) != "zh":
        return text

    result = _normalize_via_api(text)
    if result is not None:
        return result

    return _prepare_with_regex(text)


def _int_to_chinese(n: int) -> str:
    """將非負整數轉成中文讀法，例如 130 → 一百三十、2024 → 二千零二十四。"""
    if n == 0:
        return "零"
    if n < 0:
        return "負" + _int_to_chinese(-n)

    result = ""
    group_index = 0
    while n > 0:
        group = n % 10000
        if group > 0:
            chunk = _four_digits_to_chinese(group)
            chunk += _BIG_UNITS[group_index]
            if group < 1000 and result:
                chunk = "零" + chunk
            result = chunk + result
        elif result:
            result = "零" + result
        n //= 10000
        group_index += 1

    result = result.strip("零") or "零"
    if result.startswith("一十"):
        result = result[1:]
    return result


def _four_digits_to_chinese(n: int) -> str:
    digits = []
    for _ in range(4):
        digits.append(n % 10)
        n //= 10
    parts = []
    zero_pending = False
    for i in range(3, -1, -1):
        d = digits[i]
        if d == 0:
            zero_pending = True
        else:
            if zero_pending and parts:
                parts.append("零")
            zero_pending = False
            parts.append(_DIGIT_MAP[d] + _UNITS[i])
    return "".join(parts)


def _number_to_chinese(match: re.Match) -> str:
    matched_text = match.group()
    if "." in matched_text:
        integer_part, decimal_part = matched_text.split(".", 1)
        return _int_to_chinese(int(integer_part)) + "點" + "".join(_DIGIT_MAP[int(d)] for d in decimal_part)
    return _int_to_chinese(int(matched_text))


def _replace_digit(match: re.Match) -> str:
    matched_text = match.group()
    integer_part = matched_text.split(".")[0] if "." in matched_text else matched_text
    if len(integer_part) < _MIN_DIGITS:
        return matched_text
    return _number_to_chinese(match)


def _phone_to_digits(match: re.Match) -> str:
    """將電話號碼轉成逐位念法，例如 02-1234-5678 → 零二一二三四五六七八。"""
    digits_only = re.sub(r"[^\d]", "", match.group())
    return "".join(_DIGIT_MAP[int(d)] for d in digits_only)


def _replace_hotlines_with_spoken_digits(text: str) -> str:
    """Convert known hotline short codes to digit-by-digit Chinese readings."""
    return _HOTLINE_PATTERN.sub(lambda match: "".join(_DIGIT_MAP[int(d)] for d in match.group(1)), text)


def _year_to_digits(match: re.Match) -> str:
    """將年份數字逐位念，例如 2024年 → 二零二四年、113年 → 一一三年。"""
    digits = "".join(_DIGIT_MAP[int(d)] for d in match.group(1))
    return digits + "年"


def digits_to_chinese(text: str) -> str:
    """將文字中三位數以上的阿拉伯數字轉成中文讀法，保留其餘文字不變。"""
    text = _PHONE_PATTERN.sub(_phone_to_digits, text)
    text = _YEAR_PATTERN.sub(_year_to_digits, text)
    result = _DIGIT_PATTERN.sub(_replace_digit, text)
    return _LIANG_PATTERN.sub(r"兩\1", result)
