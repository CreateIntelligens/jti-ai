"""VH-398：危機回覆的專線號碼不能交給模型，也不能附上無關的衛教圖片。"""
import pytest

from app.services.crisis_reply import enforce_crisis_hotlines, is_crisis_reply


@pytest.mark.parametrize(
    "reply,expected",
    [
        # 10/13 實際發生：生命線寫成勞工諮詢專線 1955，而且是國字
        ("你可以撥打安心專線一九二五或生命線一九五五。", "你可以撥打安心專線1925或生命線1995。"),
        ("安心專線：1925，生命線：1955", "安心專線：1925，生命線：1995"),
        ("安心專線1925，生命線電話 1 9 5 5 也可以打", "安心專線1925，生命線電話 1995 也可以打"),
        ("安心專線１９２５、生命線１９９５", "安心專線1925、生命線1995"),
        ("可以打給自殺防治專線1952和生命線1995", "可以打給自殺防治專線1925和生命線1995"),
    ],
)
def test_hotline_numbers_are_forced_to_correct_values(reply, expected):
    assert enforce_crisis_hotlines(reply) == expected


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
