"""
共用工具函數
"""

from datetime import datetime
from typing import Optional


def build_date_query(mode: str, date_from: Optional[str], date_to: Optional[str]) -> dict:
    """Build a MongoDB query dict filtered by mode and optional date range."""
    query: dict = {"mode": mode}
    if date_from or date_to:
        ts_filter: dict = {}
        if date_from:
            ts_filter["$gte"] = datetime.strptime(date_from, "%Y-%m-%d")
        if date_to:
            ts_filter["$lte"] = datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        query["timestamp"] = ts_filter
    return query


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
                "first_message_time": None,
                "total": 0
            }
        sessions[sid]["conversations"].append(conv)
        sessions[sid]["total"] += 1

    # 每個 session 內的對話按 turn_number 升序排列（確保正確時序）
    for s in sessions.values():
        s["conversations"].sort(
            key=lambda c: (c.get("turn_number") or 0, c.get("timestamp") or "")
        )
        # first_message_time 取最早的 timestamp
        if s["conversations"]:
            s["first_message_time"] = s["conversations"][0].get("timestamp")

    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
    return session_list


def get_other_language(language: str) -> str:
    """Get the opposite language (en <-> zh)."""
    return "en" if language == "zh" else "zh"


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
        language = conv.get("session_snapshot", {}).get("language")
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "first_message_time": ts,
                "last_message_time": ts,
                "message_count": 0,
                "preview": (conv.get("user_message") or "")[:100] or None,
                "language": language,
            }
        else:
            # 更新 last_message_time（取較晚的）
            if ts and (not sessions[sid]["last_message_time"] or ts > sessions[sid]["last_message_time"]):
                sessions[sid]["last_message_time"] = ts
            # 更新 language（如果當前對話有且之前沒有）
            if language and not sessions[sid].get("language"):
                sessions[sid]["language"] = language
        sessions[sid]["message_count"] += 1

    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
    return session_list
