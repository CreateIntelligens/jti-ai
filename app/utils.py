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

    # 每個 session 內的對話按 turn_number 升序排列（確保正確時序）
    for s in session_list:
        s["conversations"].sort(
            key=lambda c: (c.get("turn_number") or 0, c.get("timestamp") or "")
        )
        # first_message_time 取最早的 timestamp
        if s["conversations"]:
            s["first_message_time"] = s["conversations"][0].get("timestamp")

    session_list.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
    return session_list


def group_conversations_as_summary(conversations: list) -> list:
    """
    將對話列表按 session_id 分組，回傳摘要（不含完整對話內容）。

    每個 session 包含:
    - session_id: str
    - first_message_time: str | None
    - last_message_time: str | None
    - message_count: int
    - preview: str | None（第一則 user_message 截斷）
    """
    sessions = {}
    for conv in conversations:
        sid = conv.get("session_id")
        ts = conv.get("timestamp")
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "first_message_time": ts,
                "last_message_time": ts,
                "message_count": 0,
                "preview": (conv.get("user_message") or "")[:100] or None,
            }
        else:
            # 更新 last_message_time（取較晚的）
            if ts and (not sessions[sid]["last_message_time"] or ts > sessions[sid]["last_message_time"]):
                sessions[sid]["last_message_time"] = ts
        sessions[sid]["message_count"] += 1

    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
    return session_list
