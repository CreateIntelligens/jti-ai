"""VH-398：危機回覆的專線號碼不能交給模型，也不能附上無關的衛教圖片。"""
import pytest

from app.services.crisis_reply import (
    enforce_crisis_hotlines,
    is_crisis_reply,
    is_self_harm_message,
)


@pytest.mark.parametrize(
    "reply,expected",
    [
        # 10/13 實際發生：生命線寫成勞工諮詢專線 1955，而且是國字
        ("你可以撥打安心專線一九二五或生命線一九五五。", "你可以撥打安心專線1925或生命線1995。"),
        ("安心專線：1925，生命線：1955", "安心專線：1925，生命線：1995"),
        ("安心專線1925，生命線電話 1 9 5 5 也可以打", "安心專線1925，生命線電話 1995 也可以打"),
        ("安心專線１９２５、生命線１９９５", "安心專線1925、生命線1995"),
        ("可以打給自殺防治專線1952和生命線1995", "可以打給自殺防治專線1925和生命線1995"),
        # 10/13 開發機實測：號碼寫在名稱前面，生命線還寫成 1925
        ("撥打1925安心專線或1925生命線，尋求協助。", "撥打1925安心專線或1995生命線，尋求協助。"),
        ("撥打一九二五安心專線或一九五五生命線", "撥打1925安心專線或1995生命線"),
        # 連在一起寫時，每個號碼只歸屬前面那個名稱
        ("安心專線1925生命線1995", "安心專線1925生命線1995"),
    ],
)
def test_hotline_numbers_are_forced_to_correct_values(reply, expected):
    assert enforce_crisis_hotlines(reply) == expected


def test_number_after_conjunction_belongs_to_the_next_label():
    """「安心專線或1925生命線」的 1925 屬於生命線，不能算給安心專線。"""
    fixed = enforce_crisis_hotlines("可以打安心專線或1925生命線")
    assert fixed.startswith("可以打安心專線或1995生命線")
    assert fixed.endswith("也可以撥打安心專線1925。")


def test_missing_hotline_is_appended():
    fixed = enforce_crisis_hotlines("聽起來你很辛苦，可以撥打安心專線1925聊聊。")
    assert fixed.endswith("也可以撥打生命線1995。")
    assert "1925" in fixed


def test_english_reply_is_fixed_and_completed():
    fixed = enforce_crisis_hotlines("Please reach out to Lifeline 1955.", "en")
    assert "Lifeline 1995" in fixed
    assert "suicide prevention hotline 1925" in fixed


@pytest.mark.parametrize(
    "reply",
    [
        "門診時間為上午 0830 至 1130。",
        "痛風好發於 1955 年後出生的族群，此為範例文字。",
        "PRP 注射後 48 小時內避免泡溫泉。",
    ],
)
def test_ordinary_replies_are_untouched(reply):
    assert not is_crisis_reply(reply)
    assert enforce_crisis_hotlines(reply) == reply


def test_correct_crisis_reply_is_unchanged():
    reply = "我在這裡陪你。可以撥打安心專線1925或生命線1995，也可以找信任的人說說。"
    assert is_crisis_reply(reply)
    assert enforce_crisis_hotlines(reply) == reply


def test_weakly_related_citation_carries_no_image(monkeypatch):
    """閒聊、危機訊息也會撈到帶圖段落；不夠相關就不能把圖附上（VH-398）。"""
    from app.services.base_agent import BaseAgent

    monkeypatch.delenv("RAG_IMAGE_MAX_DISTANCE", raising=False)
    close = {"text": "PRICE", "image_id": "足踝扭傷", "url": "https://x", "_distance": 0.18}
    far = {"text": "PRICE", "image_id": "足踝扭傷", "url": "https://x", "_distance": 0.33}

    assert BaseAgent._public_citation(close) == {"text": "PRICE", "image_id": "足踝扭傷", "url": "https://x"}
    assert BaseAgent._public_citation(far) == {"text": "PRICE"}


def test_image_distance_is_configurable(monkeypatch):
    from app.services.base_agent import BaseAgent

    monkeypatch.setenv("RAG_IMAGE_MAX_DISTANCE", "0.4")
    far = {"image_id": "x", "_distance": 0.33}
    assert BaseAgent._public_citation(far) == {"image_id": "x"}


def test_language_is_inferred_when_not_given():
    """OpenAI 相容 API 沒有 session 語言，英文回覆不能被補上中文句子。"""
    fixed = enforce_crisis_hotlines("Please call Lifeline 1995.")
    assert fixed.endswith("You can also call the suicide prevention hotline 1925.")
    assert enforce_crisis_hotlines("請撥打生命線1995。").endswith("也可以撥打安心專線1925。")


@pytest.mark.parametrize("raw", ["nan", "-1", "inf", "abc"])
def test_invalid_image_distance_falls_back_to_default(monkeypatch, raw):
    from app.services import base_agent

    monkeypatch.setenv("RAG_IMAGE_MAX_DISTANCE", raw)
    assert base_agent._image_max_distance() == base_agent._DEFAULT_IMAGE_MAX_DISTANCE


def test_self_harm_message_forces_hotlines_even_if_model_missed_it():
    """10/13 開發機實測：「我想從頂樓跳下去」模型只回了 119，還寫成國字。"""
    reply = "聽得到您說的話。請先撥打一一九或尋求專業人員協助。"
    assert is_self_harm_message("我想從頂樓跳下去")
    fixed = enforce_crisis_hotlines(reply, "zh", force=True)
    assert "119" in fixed and "一一九" not in fixed
    assert "安心專線1925" in fixed and "生命線1995" in fixed


@pytest.mark.parametrize(
    "message",
    ["我不想活了，想自殺", "活著好累，不如死了算了", "割腕會不會很痛", "I want to kill myself", "我想從樓頂跳下去"],
)
def test_explicit_self_harm_messages_are_detected(message):
    assert is_self_harm_message(message)


@pytest.mark.parametrize(
    "message",
    ["壓力好大", "累死了，今天門診好多人", "笑死", "我是王小明", "安眠藥一次可以吃幾顆？", "腳踝扭傷怎麼辦"],
)
def test_ordinary_messages_are_not_self_harm(message):
    assert not is_self_harm_message(message)
