"""
共用工具函數
"""

from datetime import datetime
from math import ceil
from typing import Optional


DEFAULT_HISTORY_PAGE_SIZE = 20
MAX_HISTORY_PAGE_SIZE = 100


def normalize_history_pagination(
    page: int = 1,
    page_size: int = DEFAULT_HISTORY_PAGE_SIZE,
) -> tuple[int, int]:
    """Clamp conversation-history pagination inputs to safe bounds."""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or DEFAULT_HISTORY_PAGE_SIZE), MAX_HISTORY_PAGE_SIZE))
    return page, page_size


def build_history_summary_response(
    *,
    mode: str,
    sessions: list[dict],
    total_sessions: int,
    page: int,
    page_size: int,
    extra: Optional[dict] = None,
) -> dict:
    """Build the shared summary-only conversation history list payload."""
    payload = {
        "mode": mode,
        "sessions": sessions,
        "total_conversations": sum(session.get("message_count", 0) for session in sessions),
        "total_sessions": total_sessions,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total_sessions / page_size) if total_sessions else 0,
    }
    if extra:
        payload.update(extra)
    return payload


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


def simplified_conversation_sessions(sessions: list[dict]) -> list[dict]:
    """Return export sessions with only timestamp/question/answer fields."""
    simplified = []
    for session in sessions:
        conversations = [
            {
                "timestamp": conversation.get("timestamp"),
                "question": conversation.get("user_message", ""),
                "answer": conversation.get("agent_response", ""),
            }
            for conversation in session.get("conversations", [])
        ]
        if conversations:
            simplified.append({
                "session_id": session.get("session_id"),
                "conversations": conversations,
            })
    return simplified


def filter_export_sessions_by_language(
    sessions: list[dict],
    session_manager,
    language: Optional[str],
) -> list[dict]:
    """Filter grouped export sessions by their persisted session language."""
    if not language:
        return sessions

    filtered = []
    for session in sessions:
        session_doc = session_manager.get_session(session.get("session_id"))
        if session_doc and session_doc.language == language:
            filtered.append(session)
    return filtered


def filter_session_ids_by_language(
    session_ids: list[str],
    session_manager,
    language: Optional[str],
) -> list[str]:
    """Filter session ids by their persisted session language."""
    if not language:
        return session_ids

    filtered = []
    for session_id in session_ids:
        session_doc = session_manager.get_session(session_id)
        if session_doc and session_doc.language == language:
            filtered.append(session_id)
    return filtered


def filter_conversations_by_session_language(
    conversations: list[dict],
    session_manager,
    language: Optional[str],
) -> list[dict]:
    """Filter raw conversation docs by session language, caching session lookups."""
    if not language:
        return conversations

    filtered = []
    language_by_session: dict[str, str | None] = {}
    for conversation in conversations:
        session_id = conversation.get("session_id")
        log_language = conversation.get("session_snapshot", {}).get("language")
        if log_language:
            language_by_session[session_id] = log_language
        elif session_id not in language_by_session:
            session_doc = session_manager.get_session(session_id)
            language_by_session[session_id] = session_doc.language if session_doc else None

        if language_by_session.get(session_id) == language:
            filtered.append(conversation)
    return filtered


def count_session_conversations(sessions: list[dict]) -> int:
    """Count conversations in grouped export sessions."""
    return sum(len(session.get("conversations", [])) for session in sessions)


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


class LazyProxy:
    """A lazy proxy that dynamically resolves a module or attribute on access.

    This avoids circular import cycles and stale cached references across hot-reloads.
    """

    def __init__(self, module_name: str, target_name: Optional[str] = None):
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_target_name", target_name)

    def _get_target(self):
        import sys
        import importlib

        module_name = object.__getattribute__(self, "_module_name")
        target_name = object.__getattribute__(self, "_target_name")
        module = sys.modules.get(module_name) or importlib.import_module(module_name)
        if target_name:
            return getattr(module, target_name)
        return module

    def __getattr__(self, name: str):
        return getattr(self._get_target(), name)

    def __setattr__(self, name: str, value):
        setattr(self._get_target(), name, value)

    def __delattr__(self, name: str):
        delattr(self._get_target(), name)

