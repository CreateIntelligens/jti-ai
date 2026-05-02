"""
共用工具函數
"""

from datetime import datetime
from typing import Optional


def export_sessions_by_ids(
    logger,
    session_ids: str,
    mode: str,
    store_filter: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Build session-grouped export payload from a comma-separated session_ids string.

    Returns (sessions_list, total_conversations). Each session dict has
    session_id, conversations, first_message_time, total. Sorted by
    first_message_time desc.
    """
    session_id_list = [sid.strip() for sid in session_ids.split(",") if sid.strip()]
    sessions: list[dict] = []
    total_conversations = 0
    for session_id in session_id_list:
        conversations = logger.get_session_logs(session_id)
        conversations = [c for c in conversations if c.get("mode") == mode]
        if store_filter is not None:
            conversations = [
                c for c in conversations
                if c.get("session_snapshot", {}).get("store") == store_filter
            ]
        if conversations:
            sessions.append({
                "session_id": session_id,
                "conversations": conversations,
                "first_message_time": conversations[0].get("timestamp"),
                "total": len(conversations),
            })
            total_conversations += len(conversations)
    sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
    return sessions, total_conversations


def build_date_query(
    mode: str,
    date_from: Optional[str],
    date_to: Optional[str],
    extras: Optional[dict] = None,
) -> dict:
    """Build a MongoDB query dict filtered by mode and optional date range."""
    query: dict = {"mode": mode}
    if extras:
        query.update(extras)
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
