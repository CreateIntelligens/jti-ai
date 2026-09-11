"""主頁（General 入口）開 managed app store 時要用該 app「啟用中」的 persona。

原本固定取程式碼預設，導致在主頁開 __jti__ 是 LULU 預設人設，跟同一個 app
在自己專用頁的表現不一致 —— 使用者在專用頁設了 Lady X 卻不生效。
"""

from unittest.mock import patch

from app.routers.general.chat import _app_active_persona


def test_returns_active_persona_from_app_agent():
    with patch("app.services.jti.main_agent.main_agent") as agent:
        agent._get_active_prompt_context.return_value = (
            None, "__jti__", "prompt_x", "你是 Lady X"
        )
        assert _app_active_persona("jti", "zh") == "你是 Lady X"
        agent._get_active_prompt_context.assert_called_once_with("zh")


def test_returns_none_for_unknown_app():
    assert _app_active_persona("nope", "zh") is None


def test_none_when_no_active_persona():
    """沒有啟用的自訂 persona 時回 None，讓呼叫端落回程式碼預設。"""
    with patch("app.services.jti.main_agent.main_agent") as agent:
        agent._get_active_prompt_context.return_value = (None, "__jti__", None, None)
        assert _app_active_persona("jti", "zh") is None


def test_agent_failure_does_not_break_chat():
    """persona 取不到不該讓對話開不起來。"""
    with patch("app.services.jti.main_agent.main_agent") as agent:
        agent._get_active_prompt_context.side_effect = RuntimeError("mongo down")
        assert _app_active_persona("jti", "zh") is None
