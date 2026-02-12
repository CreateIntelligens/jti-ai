"""
共用工具函數
"""


def group_conversations_by_session(conversations: list) -> list:
    """
    將對話列表按 session_id 分組，回傳按時間倒序排列的 session 列表。

    每個 session 包含:
    - session_id: str
    - conversations: list
    - first_message_time: str | None
    - total: int
    """
    sessions = {}
    for conv in conversations:
        sid = conv.get("session_id")
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "conversations": [],
                "first_message_time": conv.get("timestamp"),
                "total": 0
            }
        sessions[sid]["conversations"].append(conv)
        sessions[sid]["total"] += 1

    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x["first_message_time"], reverse=True)
    return session_list
