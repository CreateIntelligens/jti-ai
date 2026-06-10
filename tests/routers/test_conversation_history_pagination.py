import asyncio

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers.general import chat as general_chat
from app.routers.hciot import chat as hciot_chat
from app.routers.jti import chat as jti_chat


class SummaryLogger:
    def __init__(self, total_sessions=45):
        self.total_sessions = total_sessions
        self.paginated_calls = []
        self.summary_calls = []
        self.full_logs_calls = []

    def get_paginated_session_ids(self, query, page, page_size):
        self.paginated_calls.append({"query": query, "page": page, "page_size": page_size})
        return ["session-a", "session-b"], self.total_sessions

    def get_session_summaries(self, session_ids, query=None):
        self.summary_calls.append({"session_ids": list(session_ids), "query": query})
        return [
            {
                "session_id": "session-a",
                "first_message_time": "2026-06-01T10:00:00",
                "last_message_time": "2026-06-01T10:03:00",
                "message_count": 3,
                "preview": "hello",
                "language": "zh",
            },
            {
                "session_id": "session-b",
                "first_message_time": "2026-06-01T09:00:00",
                "last_message_time": "2026-06-01T09:01:00",
                "message_count": 1,
                "preview": "hi",
                "language": "en",
            },
        ]

    def get_logs_for_sessions(self, session_ids):
        self.full_logs_calls.append(list(session_ids))
        raise AssertionError("history list must not load full conversation logs")

    def get_session_logs(self, session_id):
        return [
            {
                "_id": "log-1",
                "session_id": session_id,
                "mode": "jti",
                "turn_number": 1,
                "timestamp": "2026-06-01T10:00:00",
                "user_message": "hello",
                "agent_response": "world",
                "tool_calls": [],
                "session_snapshot": {"language": "zh"},
            },
        ]


def test_jti_history_list_uses_requested_page_and_summary_payload(monkeypatch):
    logger = SummaryLogger(total_sessions=45)
    monkeypatch.setattr(jti_chat, "_get_conversation_logger", lambda: logger)

    payload = asyncio.run(jti_chat.get_conversations(page=2, page_size=20))

    assert logger.paginated_calls == [
        {"query": {"mode": "jti"}, "page": 2, "page_size": 20},
    ]
    assert logger.summary_calls == [
        {"session_ids": ["session-a", "session-b"], "query": {"mode": "jti"}},
    ]
    assert logger.full_logs_calls == []
    assert payload["page"] == 2
    assert payload["page_size"] == 20
    assert payload["total_sessions"] == 45
    assert payload["total_pages"] == 3
    assert payload["total_conversations"] == 4
    assert payload["sessions"][0]["session_id"] == "session-a"
    assert "conversations" not in payload["sessions"][0]


def test_hciot_history_list_clamps_pagination_and_uses_summaries(monkeypatch):
    logger = SummaryLogger(total_sessions=45)
    monkeypatch.setattr(hciot_chat, "_get_conversation_logger", lambda: logger)

    payload = asyncio.run(hciot_chat.get_conversations(page=0, page_size=500))

    assert logger.paginated_calls == [
        {"query": {"mode": "hciot"}, "page": 1, "page_size": 100},
    ]
    assert logger.summary_calls == [
        {"session_ids": ["session-a", "session-b"], "query": {"mode": "hciot"}},
    ]
    assert logger.full_logs_calls == []
    assert payload["page"] == 1
    assert payload["page_size"] == 100
    assert payload["total_pages"] == 1


def test_general_history_list_uses_store_filter_with_summary_pagination(monkeypatch):
    logger = SummaryLogger(total_sessions=11)
    monkeypatch.setattr(general_chat, "_get_conversation_logger", lambda: logger)

    payload = general_chat.get_general_conversations(
        store_name="store-a",
        date_from="2026-06-01",
        page=3,
        page_size=5,
    )

    expected_query = {
        "mode": "general",
        "$or": [
            {"store_name": "store-a"},
            {"session_snapshot.store": "store-a"},
        ],
        "timestamp": {"$gte": general_chat.datetime.strptime("2026-06-01", "%Y-%m-%d")},
    }
    assert logger.paginated_calls == [
        {"query": expected_query, "page": 3, "page_size": 5},
    ]
    assert logger.summary_calls == [
        {"session_ids": ["session-a", "session-b"], "query": expected_query},
    ]
    assert logger.full_logs_calls == []
    assert payload["page"] == 3
    assert payload["page_size"] == 5
    assert payload["total_pages"] == 3
    assert payload["total_conversations"] == 4


def test_jti_history_detail_still_returns_full_conversations(monkeypatch):
    logger = SummaryLogger()
    monkeypatch.setattr(jti_chat, "_get_conversation_logger", lambda: logger)

    payload = asyncio.run(jti_chat.get_conversations(session_id="session-a"))

    assert logger.paginated_calls == []
    assert logger.summary_calls == []
    assert payload["session_id"] == "session-a"
    assert payload["total"] == 1
    assert payload["conversations"][0]["user_message"] == "hello"
