"""危機（自傷）回覆的硬性保護：專線號碼不交給模型，也不附衛教圖片。

是否為危機回覆由模型在 safety prompt 下自己判斷；這裡只看它的回覆有沒有提到
危機專線，再把號碼固定成正確值。號碼寫錯（例如生命線寫成 1955，那是勞工諮詢
專線）會延誤求助，所以不能只靠 prompt 要求模型照抄。
"""

from __future__ import annotations

import re

from app.services.safety_numbers import LIFELINE, SUICIDE_PREVENTION_HOTLINE

_DIGIT = "[0-9０-９〇零一二三四五六七八九]"
_NUMBER = rf"{_DIGIT}(?:[ -]?{_DIGIT}){{2,3}}"
# 專線名稱與號碼之間常見的連接字，例如「生命線：」「生命線是」「生命線電話」
_GAP = r"[^0-9０-９〇零一二三四五六七八九。，,；;！!？?\n]{0,8}?"

# (名稱的 regex, 正確號碼, 補充時用的中文名稱, 英文名稱)
_HOTLINES = (
    (r"安心專線|自殺防治(?:專線|安心專線)?", SUICIDE_PREVENTION_HOTLINE, "安心專線", "suicide prevention hotline"),
    (r"生命線", LIFELINE, "生命線", "Lifeline"),
)
_EN_HOTLINES = (
    (r"suicide prevention (?:hotline|line|center)", SUICIDE_PREVENTION_HOTLINE),
    (r"lifeline", LIFELINE),
)
_SPOKEN_FORMS = {
    SUICIDE_PREVENTION_HOTLINE.translate(str.maketrans("0123456789", "〇一二三四五六七八九")): SUICIDE_PREVENTION_HOTLINE,
    LIFELINE.translate(str.maketrans("0123456789", "〇一二三四五六七八九")): LIFELINE,
}
_CRISIS_MARKERS = re.compile(
    r"安心專線|生命線|自殺防治|suicide prevention|lifeline"
    rf"|(?<!\d){SUICIDE_PREVENTION_HOTLINE}(?!\d)|(?<!\d){LIFELINE}(?!\d)",
    re.IGNORECASE,
)


def is_crisis_reply(text: str) -> bool:
    return bool(text) and bool(_CRISIS_MARKERS.search(text))


def enforce_crisis_hotlines(text: str, language: str = "zh") -> str:
    """把危機回覆裡的專線號碼改成正確值，缺的補上；不是危機回覆就原樣回傳。"""
    if not is_crisis_reply(text):
        return text

    for spoken, digits in _SPOKEN_FORMS.items():
        text = text.replace(spoken, digits)

    for label, number, _zh, _en in _HOTLINES:
        text = re.sub(
            rf"({label})({_GAP})({_NUMBER})",
            lambda m, n=number: f"{m.group(1)}{m.group(2)}{n}",
            text,
        )
    for label, number in _EN_HOTLINES:
        text = re.sub(
            rf"({label})({_GAP})({_NUMBER})",
            lambda m, n=number: f"{m.group(1)}{m.group(2)}{n}",
            text,
            flags=re.IGNORECASE,
        )

    missing = [
        (zh, en, number)
        for _label, number, zh, en in _HOTLINES
        if not re.search(rf"(?<!\d){number}(?!\d)", text)
    ]
    if not missing:
        return text
    if language == "en":
        names = " or ".join(f"the {en} {number}" for _zh, en, number in missing)
        return f"{text.rstrip()} You can also call {names}."
    names = "或".join(f"{zh}{number}" for zh, _en, number in missing)
    return f"{text.rstrip()}也可以撥打{names}。"
