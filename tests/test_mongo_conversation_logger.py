"""
MongoDB ConversationLogger 單元測試

測試項目：
1. 記錄對話
2. 查詢對話
3. 統計和分析
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.services.logging.mongo_conversation_logger import MongoConversationLogger


class TestMongoConversationLogger(unittest.TestCase):
    """MongoDB ConversationLogger 測試"""

    @patch("app.services.logging.mongo_conversation_logger.get_mongo_db")
    def setUp(self, mock_get_db):
        """測試前準備"""
        self.mock_db = MagicMock()
        mock_get_db.return_value = self.mock_db

        # 模擬 conversations 集合
        self.mock_conversations = MagicMock()
        self.mock_db.__getitem__.return_value = self.mock_conversations

        self.logger = MongoConversationLogger()

    def test_log_conversation_first_turn(self):
        """測試記錄對話（第一輪）"""
        # 模擬沒有現有對話
        self.mock_conversations.find_one.return_value = None

        # 模擬 insert_one
        mock_result = MagicMock()
        mock_result.inserted_id = "log_id_1"
        self.mock_conversations.insert_one.return_value = mock_result

        log_id = self.logger.log_conversation(
            session_id="test-123",
            mode="jti",
            user_message="開始測驗",
            agent_response="好的，開始色彩測驗",
            tool_calls=[],
            session_state={"step": "quiz"}
        )

        # 驗證
        self.assertEqual(log_id, "log_id_1")
        self.mock_conversations.insert_one.assert_called_once()

        # 驗證記錄內容
        call_args = self.mock_conversations.insert_one.call_args
        log_entry = call_args[0][0]
        self.assertEqual(log_entry["session_id"], "test-123")
        self.assertEqual(log_entry["mode"], "jti")
        self.assertEqual(log_entry["turn_number"], 1)
        self.assertEqual(log_entry["user_message"], "開始測驗")

    def test_log_conversation_subsequent_turns(self):
        """測試記錄對話（後續輪次）"""
        # 模擬現有對話
        mock_last_turn = {"turn_number": 2}
        self.mock_conversations.find_one.return_value = mock_last_turn

        mock_result = MagicMock()
        mock_result.inserted_id = "log_id_2"
        self.mock_conversations.insert_one.return_value = mock_result

        log_id = self.logger.log_conversation(
            session_id="test-123",
            mode="jti",
            user_message="我選擇 A",
            agent_response="好的，記錄了你的答案"
        )

        # 驗證
        self.assertEqual(log_id, "log_id_2")

        # 驗證 turn_number 是遞增的
        call_args = self.mock_conversations.insert_one.call_args
        log_entry = call_args[0][0]
        self.assertEqual(log_entry["turn_number"], 3)  # 2 + 1

    def test_get_session_logs(self):
        """測試取得 session 的所有日誌"""
        mock_logs = [
            {
                "_id": MagicMock(),
                "session_id": "test-123",
                "turn_number": 1,
                "timestamp": datetime.now(),
                "user_message": "開始測驗",
                "agent_response": "好的",
                "tool_calls": [],
                "session_snapshot": {}
            },
            {
                "_id": MagicMock(),
                "session_id": "test-123",
                "turn_number": 2,
                "timestamp": datetime.now(),
                "user_message": "選擇 A",
                "agent_response": "已記錄",
                "tool_calls": [],
                "session_snapshot": {}
            }
        ]

        # 模擬 find 和 sort
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(mock_logs)
        self.mock_conversations.find.return_value = mock_cursor

        logs = self.logger.get_session_logs("test-123")

        # 驗證
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["turn_number"], 1)
        self.assertEqual(logs[1]["turn_number"], 2)

    def test_get_session_logs_with_limit(self):
        """測試取得 session 日誌（限制筆數）"""
        mock_logs = [
            {
                "_id": MagicMock(),
                "session_id": "test-123",
                "turn_number": i,
                "timestamp": datetime.now(),
                "user_message": f"message {i}",
                "agent_response": f"response {i}",
                "tool_calls": [],
                "session_snapshot": {}
            }
            for i in range(1, 11)
        ]

        # 模擬 find, sort 和 limit
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(mock_logs[:5])
        self.mock_conversations.find.return_value = mock_cursor

        logs = self.logger.get_session_logs("test-123", limit=5)

        # 驗證
        self.assertEqual(len(logs), 5)
        self.mock_conversations.find.return_value.limit.assert_called_once_with(5)

    def test_list_sessions(self):
        """測試列出所有有對話的 sessions"""
        mock_results = [
            {"_id": "session-1"},
            {"_id": "session-2"},
            {"_id": "session-3"}
        ]

        self.mock_conversations.aggregate.return_value = mock_results

        sessions = self.logger.list_sessions()

        # 驗證
        self.assertEqual(len(sessions), 3)
        self.assertIn("session-1", sessions)
        self.assertIn("session-2", sessions)
        self.assertIn("session-3", sessions)

    def test_get_statistics(self):
        """測試取得統計資訊"""
        self.mock_conversations.count_documents.return_value = 100

        self.mock_conversations.aggregate.side_effect = [
            [{"_id": "jti", "count": 60}, {"_id": "general", "count": 40}],  # mode stats
            [{"_id": None, "avg": 5.5}],  # avg turns
            [{"_id": "color_quiz", "count": 50}, {"_id": "product_search", "count": 30}]  # tool stats
        ]

        stats = self.logger.get_statistics()

        # 驗證
        self.assertEqual(stats["total_conversations"], 100)
        self.assertEqual(stats["mode_distribution"]["jti"], 60)
        self.assertEqual(stats["mode_distribution"]["general"], 40)
        self.assertEqual(stats["avg_turns_per_session"], 5.5)
        self.assertEqual(stats["tool_usage"]["color_quiz"], 50)

    def test_get_conversations_by_date_range(self):
        """測試按日期範圍查詢"""
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()

        mock_conversations = [
            {
                "_id": MagicMock(),
                "session_id": "test-1",
                "timestamp": datetime.now(),
                "mode": "jti",
                "user_message": "msg 1",
                "agent_response": "resp 1",
                "tool_calls": [],
                "session_snapshot": {}
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(mock_conversations)
        self.mock_conversations.find.return_value = mock_cursor

        results = self.logger.get_conversations_by_date_range(
            start_date,
            end_date,
            mode="jti"
        )

        # 驗證
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["mode"], "jti")

    def test_get_tool_call_statistics(self):
        """測試工具呼叫統計"""
        mock_stats = [
            {
                "_id": "quiz_tool",
                "count": 100,
                "avg_execution_time": 250.5
            },
            {
                "_id": "search_tool",
                "count": 50,
                "avg_execution_time": 150.0
            }
        ]

        self.mock_conversations.aggregate.return_value = mock_stats

        stats = self.logger.get_tool_call_statistics()

        # 驗證
        self.assertEqual(stats["quiz_tool"]["count"], 100)
        self.assertEqual(stats["quiz_tool"]["avg_execution_time_ms"], 250.5)
        self.assertEqual(stats["search_tool"]["count"], 50)

    def test_delete_old_logs(self):
        """測試刪除舊日誌"""
        mock_result = MagicMock()
        mock_result.deleted_count = 15
        self.mock_conversations.delete_many.return_value = mock_result

        deleted_count = self.logger.delete_old_logs(days=30)

        # 驗證
        self.assertEqual(deleted_count, 15)
        self.mock_conversations.delete_many.assert_called_once()

        # 驗證查詢條件
        call_args = self.mock_conversations.delete_many.call_args
        query = call_args[0][0]
        self.assertIn("timestamp", query)
        self.assertIn("$lt", query["timestamp"])


if __name__ == "__main__":
    unittest.main()
