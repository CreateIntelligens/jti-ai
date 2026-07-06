from app.models.session import Session
from app.services.esg.main_agent import _build_session_state as build_esg_session_state
from app.services.general.main_agent import MainAgent as GeneralAgent
from app.services.hciot.main_agent import _build_session_state as build_hciot_session_state
from app.services.jti.main_agent import _build_session_state as build_jti_session_state


def test_zh_session_states_expose_utc8_datetime_guidance():
    session = Session(language="zh")
    states = [
        build_jti_session_state(session),
        build_hciot_session_state(session),
        build_esg_session_state(session),
        GeneralAgent()._get_session_state(session),
    ]

    for state in states:
        assert "目前日期時間（UTC+8）:" in state
        assert "昨天是" in state
        assert "今天是" in state
        assert "明天是" in state
        assert "判斷今天、目前日期、星期幾、現在時間或時區" in state
        assert "今天要掛號" in state
        assert "不要查詢知識庫" not in state
        assert "不要視為無關問題" not in state


def test_en_session_states_expose_utc8_datetime_guidance():
    session = Session(language="en")
    states = [
        build_jti_session_state(session),
        build_hciot_session_state(session),
        build_esg_session_state(session),
        GeneralAgent()._get_session_state(session),
    ]

    for state in states:
        assert "Current date/time (UTC+8):" in state
        assert "Yesterday was" in state
        assert "Today is" in state
        assert "Tomorrow is" in state
        assert "interpret today, the current date, the weekday" in state
        assert "book an appointment today" in state
        assert "do not search the knowledge base" not in state
        assert "treat it as off-topic" not in state
