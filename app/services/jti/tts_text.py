"""Helpers for preparing TTS text."""

from __future__ import annotations

import re
from typing import Optional

try:
    from opencc import OpenCC  # type: ignore
except Exception:  # pragma: no cover - fallback when dependency is unavailable
    OpenCC = None  # type: ignore

_T2S_CONVERTER = OpenCC("t2s") if OpenCC else None

_DIGIT_MAP = "零一二三四五六七八九"
_UNITS = ["", "十", "百", "千"]
_BIG_UNITS = ["", "萬", "億"]
_DIGIT_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_LIANG_PATTERN = re.compile(r"二([百千萬億])")
# 電話號碼：數字群組以 - 或空格分隔，至少兩段，例如 02-1234-5678 或 0800 123 456
_PHONE_PATTERN = re.compile(r"\(?\d+\)?[\-\s]?\d[\d\-\s]{4,}\d")
# 年份：4位數字後接「年」字，逐位念（西元年）
_YEAR_PATTERN = re.compile(r"(\d{4})年")
_MIN_DIGITS = 3


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
    for i in range(4):
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
    s = match.group()
    if "." in s:
        integer_part, decimal_part = s.split(".", 1)
        return _int_to_chinese(int(integer_part)) + "點" + "".join(_DIGIT_MAP[int(d)] for d in decimal_part)
    return _int_to_chinese(int(s))


def _replace_digit(match: re.Match) -> str:
    s = match.group()
    integer_part = s.split(".")[0] if "." in s else s
    if len(integer_part) < _MIN_DIGITS:
        return s
    return _number_to_chinese(match)


def _phone_to_digits(match: re.Match) -> str:
    """將電話號碼轉成逐位念法，例如 02-1234-5678 → 零二一二三四五六七八。"""
    digits_only = re.sub(r"[^\d]", "", match.group())
    return "".join(_DIGIT_MAP[int(d)] for d in digits_only)


def _year_to_digits(match: re.Match) -> str:
    """將年份數字逐位念，例如 2024年 → 二零二四年、113年 → 一一三年。"""
    digits = "".join(_DIGIT_MAP[int(d)] for d in match.group(1))
    return digits + "年"


def digits_to_chinese(text: str) -> str:
    """將文字中三位數以上的阿拉伯數字轉成中文讀法，保留其餘文字不變。
    電話號碼格式（數字-數字）轉成逐位念法。
    年份（數字後接「年」字）逐位念。
    """
    text = _PHONE_PATTERN.sub(_phone_to_digits, text)
    text = _YEAR_PATTERN.sub(_year_to_digits, text)
    result = _DIGIT_PATTERN.sub(_replace_digit, text)
    return _LIANG_PATTERN.sub(r"兩\1", result)


def to_tts_text(text: Optional[str], language: str) -> Optional[str]:
    """
    Prepare text for TTS.

    - Non-Chinese languages: keep original text
    - Chinese: convert digits to Chinese reading, then Traditional to Simplified
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

    text = digits_to_chinese(text)

    if not _T2S_CONVERTER:
        return text

    try:
        return _T2S_CONVERTER.convert(text)
    except Exception:
        return text

