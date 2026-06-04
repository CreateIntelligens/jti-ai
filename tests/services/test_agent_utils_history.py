"""build_chat_history 滑動視窗與角色對齊行為。

防呆視窗：每次請求帶給 Gemini 的歷史上限為 MAX_HISTORY_MESSAGES 則，
取尾後須確保第一筆為 user 角色（Gemini 要求 history 以 user 開頭）。
MongoDB 仍儲存完整歷史，這裡只驗證「餵模型時」的裁切。
"""

from app.services.agent_utils import MAX_HISTORY_MESSAGES, build_chat_history


def _make_history(n: int) -> list[dict]:
    """產生 n 則交替 user/model 的歷史（第 0 則為 user）。"""
    return [
        {"role": "user" if i % 2 == 0 else "model", "content": f"msg-{i}"}
        for i in range(n)
    ]


def _texts(contents) -> list[str]:
    return [c.parts[0].text for c in contents]


def test_history_within_limit_is_returned_in_full():
    history = _make_history(MAX_HISTORY_MESSAGES - 2)
    contents = build_chat_history(history)
    texts = _texts(contents)

    assert len(contents) == len(history)
    assert texts[0] == "msg-0"
    assert texts[-1] == f"msg-{len(history) - 1}"


def test_history_over_limit_keeps_only_most_recent_window():
    total = MAX_HISTORY_MESSAGES + 10
    history = _make_history(total)
    contents = build_chat_history(history)
    texts = _texts(contents)

    # 視窗最多 MAX_HISTORY_MESSAGES 則（角色對齊可能再少一則，見下個測試）。
    assert len(contents) <= MAX_HISTORY_MESSAGES
    # 最後一則永遠是最新的原始訊息，不會被裁掉。
    assert texts[-1] == f"msg-{total - 1}"
    # 最舊的訊息已被丟出視窗。
    assert "msg-0" not in texts


def test_window_is_realigned_to_start_with_user():
    # 偶數則的視窗，純取尾會讓開頭落在 model 角色（msg-1）。
    # MAX_HISTORY_MESSAGES 為偶數時，total 為奇數則切尾開頭會是 model，
    # 對齊邏輯應往後再裁一則，使第一筆為 user。
    history = _make_history(MAX_HISTORY_MESSAGES + 1)
    contents = build_chat_history(history)

    assert contents[0].role == "user"
    # 對齊後視窗比上限少一則。
    assert len(contents) == MAX_HISTORY_MESSAGES - 1


def test_empty_history_returns_empty():
    assert build_chat_history([]) == []


def test_roles_are_mapped_to_gemini_user_and_model():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},  # 非 user 一律映射成 model
        {"role": "model", "content": "world"},
    ]
    contents = build_chat_history(history)

    assert [c.role for c in contents] == ["user", "model", "model"]
