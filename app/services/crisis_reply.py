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
# 名稱與號碼之間的連接字（「生命線：」「生命線是」「生命線電話」）。不能跨過「或、和、、」等
# 連接詞，否則「安心專線或1925生命線」會把屬於生命線的號碼算給安心專線。
_GAP = r"[^0-9０-９〇零一二三四五六七八九。，,；;！!？?\n或和及與跟、]{0,6}?"

_ZH_SUICIDE_LABEL = r"安心專線|自殺防治(?:專線|安心專線)?"
_ZH_LIFELINE_LABEL = r"生命線"
# 由左到右一次掃描，每個號碼只歸屬一個名稱：「名稱+號碼」或「號碼+名稱」。
# 這樣「安心專線1925生命線1995」不會把 1925 誤認成生命線的號碼。
_ZH_PAIR = re.compile(
    rf"(?P<label>{_ZH_SUICIDE_LABEL}|{_ZH_LIFELINE_LABEL})(?P<gap>{_GAP})(?P<num>{_NUMBER})"
    rf"|(?P<num2>{_NUMBER})(?P<gap2>[ 　:：]{{0,2}})(?P<label2>{_ZH_SUICIDE_LABEL}|{_ZH_LIFELINE_LABEL})"
)
_EN_LABEL = r"suicide prevention (?:hotline|line|center)|lifeline"
_EN_PAIR = re.compile(
    rf"(?P<label>{_EN_LABEL})(?P<gap>[ :(\-]{{0,3}}(?:at |on )?)(?P<num>{_NUMBER})"
    rf"|(?P<num2>{_NUMBER})(?P<gap2>[ :(]{{0,2}})(?P<label2>{_EN_LABEL})",
    re.IGNORECASE,
)
_MISSING_NAMES = (
    (SUICIDE_PREVENTION_HOTLINE, "安心專線", "suicide prevention hotline"),
    (LIFELINE, "生命線", "Lifeline"),
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


# 使用者明確說出自傷意圖。模型偶爾會漏判（10/13「我想從頂樓跳下去」只回了 119），
# 這時仍要當危機處理。寧可對玩笑話多補一句專線，也不要漏掉真正的危機。
_SELF_HARM_MESSAGE = re.compile(
    r"自殺|自殘|自傷|輕生|想死|不想活|活不下去|(?:死掉|死了)算了|不如死|結束(?:自己的)?生命|傷害自己|割腕|上吊|燒炭|跳樓"
    r"|(?:頂樓|樓頂|高樓|陽台|橋上).{0,4}跳"
    r"|suicid|kill myself|end my life|want to die|don't want to live|do not want to live|hurt myself|self[- ]harm",
    re.IGNORECASE,
)


def is_self_harm_message(user_message: str) -> bool:
    return bool(user_message) and bool(_SELF_HARM_MESSAGE.search(user_message))


def _number_for(label: str) -> str:
    return LIFELINE if re.fullmatch(_ZH_LIFELINE_LABEL + "|lifeline", label, re.IGNORECASE) else SUICIDE_PREVENTION_HOTLINE


def _fix_pair(match: re.Match) -> str:
    if match.group("label"):
        return f"{match.group('label')}{match.group('gap')}{_number_for(match.group('label'))}"
    return f"{_number_for(match.group('label2'))}{match.group('gap2')}{match.group('label2')}"


def is_crisis_reply(text: str) -> bool:
    return bool(text) and bool(_CRISIS_MARKERS.search(text))


def enforce_crisis_hotlines(
    text: str,
    language: str | None = None,
    force: bool = False,
) -> str:
    """把危機回覆裡的專線號碼改成正確值，缺的補上；不是危機回覆就原樣回傳。

    force=True 表示已從使用者訊息判定為危機，即使回覆沒提到專線也要補上。
    language 沒給時依回覆內容判斷（含中日韓文字就當中文），補上的句子才不會語言錯置。
    """
    if not force and not is_crisis_reply(text):
        return text
    if language is None:
        language = "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"

    for spoken, digits in _SPOKEN_FORMS.items():
        text = text.replace(spoken, digits)
    text = text.replace("一一九", "119")
    text = _ZH_PAIR.sub(_fix_pair, text)
    text = _EN_PAIR.sub(_fix_pair, text)

    missing = [
        (zh, en, number)
        for number, zh, en in _MISSING_NAMES
        if not re.search(rf"(?<!\d){number}(?!\d)", text)
    ]
    if not missing:
        return text
    if language == "en":
        names = " or ".join(f"the {en} {number}" for _zh, en, number in missing)
        return f"{text.rstrip()} You can also call {names}."
    names = "或".join(f"{zh}{number}" for zh, _en, number in missing)
    return f"{text.rstrip()}也可以撥打{names}。"
