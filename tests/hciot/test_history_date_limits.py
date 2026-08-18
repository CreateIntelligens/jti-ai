import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.routers.hciot.chat import _get_months_ago
from tests.support.app_test_support import get_test_app, override_admin_auth

app = get_test_app()
_TZ_TAIPEI = timezone(timedelta(hours=8))


class TestHciotHistoryDateLimits(unittest.TestCase):
    def setUp(self):
        self.auth_patcher = patch("app.auth.verify_auth", return_value={"role": "admin", "store_name": None})
        self.auth_patcher.start()
        self.cleanup_auth = override_admin_auth(app)
        self.client = TestClient(app)

    def tearDown(self):
        self.cleanup_auth()
        self.auth_patcher.stop()

    def test_get_months_ago_calculation(self):
        base = datetime(2026, 8, 18, tzinfo=_TZ_TAIPEI)
        self.assertEqual(_get_months_ago(3, base).isoformat(), "2026-05-18")
        self.assertEqual(_get_months_ago(6, base).isoformat(), "2026-02-18")

        # Edge case: Leap year / 31st to 28th
        base_march31 = datetime(2026, 3, 31, tzinfo=_TZ_TAIPEI)
        self.assertEqual(_get_months_ago(1, base_march31).isoformat(), "2026-02-28")

    def test_get_conversations_rejects_date_from_beyond_six_months(self):
        too_early = "2020-01-01"
        response = self.client.get(
            f"/api/hciot-admin/conversations?date_from={too_early}",
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("查詢區間限制為半年內", response.json()["detail"])

    def test_get_conversations_rejects_end_date_before_start_date(self):
        response = self.client.get(
            "/api/hciot-admin/conversations?date_from=2026-08-01&date_to=2026-07-01",
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("結束日期不能早於開始日期", response.json()["detail"])

    def test_get_conversations_accepts_valid_six_month_query(self):
        valid_date = _get_months_ago(5).isoformat()
        with (
            patch("app.routers.hciot.chat._get_conversation_logger") as mock_logger_getter,
        ):
            mock_logger = mock_logger_getter.return_value
            mock_logger.get_paginated_session_ids = MagicMock(return_value=([], 0))
            mock_logger.get_session_summaries = MagicMock(return_value=[])

            response = self.client.get(
                f"/api/hciot-admin/conversations?date_from={valid_date}",
                headers={"Origin": "http://testserver"},
            )
            self.assertEqual(response.status_code, 200)

    def test_export_conversations_rejects_date_from_beyond_three_months(self):
        four_months_ago = (_get_months_ago(4) - timedelta(days=5)).isoformat()
        response = self.client.get(
            f"/api/hciot-admin/conversations/export?date_from={four_months_ago}",
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("下載區間限制為近三個月內", response.json()["detail"])

    def test_export_conversations_accepts_valid_three_month_date(self):
        two_months_ago = _get_months_ago(2).isoformat()
        with (
            patch("app.routers.hciot.chat._get_conversation_logger") as mock_logger_getter,
            patch("app.routers.hciot.chat._get_session_manager") as mock_session_getter,
        ):
            mock_logger = mock_logger_getter.return_value
            mock_logger.get_paginated_session_ids = MagicMock(return_value=([], 0))
            mock_logger.get_logs_for_sessions = MagicMock(return_value=[])
            mock_session = mock_session_getter.return_value
            mock_session.filter_session_ids_by_language = MagicMock(return_value=[])

            response = self.client.get(
                f"/api/hciot-admin/conversations/export?date_from={two_months_ago}",
                headers={"Origin": "http://testserver"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("exported_at", response.json())

    def test_export_conversations_by_session_ids_filters_older_than_three_months(self):
        three_months_ago = _get_months_ago(3).isoformat()
        old_time = "2020-01-01T12:00:00"
        recent_time = f"{three_months_ago}T12:00:00"

        fake_raw_sessions = [
            {
                "session_id": "sid-1",
                "conversations": [
                    {
                        "session_id": "sid-1",
                        "mode": "hciot",
                        "timestamp": old_time,
                        "user_message": "old",
                        "agent_response": "old ans",
                    },
                    {
                        "session_id": "sid-1",
                        "mode": "hciot",
                        "timestamp": recent_time,
                        "user_message": "new",
                        "agent_response": "new ans",
                    },
                ],
                "first_message_time": old_time,
                "total": 2,
            },
            {
                "session_id": "sid-old-only",
                "conversations": [
                    {
                        "session_id": "sid-old-only",
                        "mode": "hciot",
                        "timestamp": old_time,
                        "user_message": "old2",
                        "agent_response": "old ans2",
                    },
                ],
                "first_message_time": old_time,
                "total": 1,
            }
        ]

        with (
            patch("app.routers.hciot.chat.export_sessions_by_ids", new=MagicMock(return_value=(fake_raw_sessions, 3))),
            patch("app.routers.hciot.chat._get_conversation_logger"),
            patch("app.routers.hciot.chat._get_session_manager"),
        ):
            response = self.client.get(
                "/api/hciot-admin/conversations/export?session_ids=sid-1,sid-old-only",
                headers={"Origin": "http://testserver"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            # Only sid-1 should remain, and only with the recent conversation
            self.assertEqual(len(payload["sessions"]), 1)
            self.assertEqual(payload["sessions"][0]["session_id"], "sid-1")
            self.assertEqual(len(payload["sessions"][0]["conversations"]), 1)
            self.assertEqual(payload["sessions"][0]["conversations"][0]["timestamp"], recent_time)


if __name__ == "__main__":
    unittest.main()
