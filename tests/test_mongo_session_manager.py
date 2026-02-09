"""
MongoDB SessionManager 單元測試

測試項目：
1. CRUD 操作
2. 狀態轉換
3. 過期清理
4. 查詢功能
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models.session import Session, SessionStep, GameMode


class TestMongoSessionManager(unittest.TestCase):
    """MongoDB SessionManager 測試"""

    @patch("app.services.mongo_session_manager.get_mongo_db")
    def setUp(self, mock_get_db):
        """測試前準備"""
        self.mock_db = MagicMock()
        mock_get_db.return_value = self.mock_db

        # 模擬 sessions 集合
        self.mock_sessions = MagicMock()
        self.mock_db.__getitem__.return_value = self.mock_sessions

        from app.services.mongo_session_manager import MongoSessionManager
        self.manager = MongoSessionManager()

    def test_create_session(self):
        """測試建立 session"""
        # 模擬 insert_one
        mock_result = MagicMock()
        mock_result.inserted_id = "test_id"
        self.mock_sessions.insert_one.return_value = mock_result

        session = self.manager.create_session(
            mode=GameMode.COLOR,
            language="zh"
        )

        # 驗證
        self.assertIsNotNone(session)
        self.assertEqual(session.mode, GameMode.COLOR)
        self.assertEqual(session.language, "zh")
        self.assertEqual(session.step, SessionStep.INITIAL)

        # 驗證 insert_one 被呼叫
        self.mock_sessions.insert_one.assert_called_once()

    def test_get_session(self):
        """測試取得 session"""
        # 模擬 MongoDB document
        mock_doc = {
            "session_id": "test-123",
            "mode": "color_taste",
            "language": "zh",
            "step": "initial",
            "current_q_index": 0,
            "answers": {},
            "current_question": None,
            "selected_questions": None,
            "chat_history": [],
            "color_result_id": None,
            "color_scores": {},
            "color_result": None,
            "quiz_id": "color_taste",
            "updated_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=30)
        }

        self.mock_sessions.find_one.return_value = mock_doc

        session = self.manager.get_session("test-123")

        # 驗證
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, "test-123")
        self.assertEqual(session.mode, GameMode.COLOR)

        # 驗證 find_one 被呼叫
        self.mock_sessions.find_one.assert_called_once_with(
            {"session_id": "test-123"}
        )

    def test_get_session_expired(self):
        """測試取得已過期的 session"""
        # 模擬已過期的 document
        mock_doc = {
            "session_id": "test-123",
            "mode": "color_taste",
            "language": "zh",
            "step": "initial",
            "current_q_index": 0,
            "answers": {},
            "current_question": None,
            "selected_questions": None,
            "chat_history": [],
            "color_result_id": None,
            "color_scores": {},
            "color_result": None,
            "quiz_id": "color_taste",
            "updated_at": datetime.now() - timedelta(hours=1),
            "expires_at": datetime.now() - timedelta(minutes=10)  # 已過期
        }

        self.mock_sessions.find_one.return_value = mock_doc

        session = self.manager.get_session("test-123")

        # 驗證返回 None（因為已過期）
        self.assertIsNone(session)

        # 驗證 delete_one 被呼叫（清理過期 session）
        self.mock_sessions.delete_one.assert_called_once()

    def test_update_session(self):
        """測試更新 session"""
        session = Session(mode=GameMode.COLOR, language="zh")
        session.step = SessionStep.QUIZ

        # 模擬 update_one
        mock_result = MagicMock()
        mock_result.matched_count = 1
        self.mock_sessions.update_one.return_value = mock_result

        updated = self.manager.update_session(session)

        # 驗證
        self.assertIsNotNone(updated)
        self.assertEqual(updated.step, SessionStep.QUIZ)

        # 驗證 update_one 被呼叫
        self.mock_sessions.update_one.assert_called_once()

    def test_delete_session(self):
        """測試刪除 session"""
        # 模擬 delete_one
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        self.mock_sessions.delete_one.return_value = mock_result

        result = self.manager.delete_session("test-123")

        # 驗證
        self.assertTrue(result)

        # 驗證 delete_one 被呼叫
        self.mock_sessions.delete_one.assert_called_once_with(
            {"session_id": "test-123"}
        )

    def test_start_quiz(self):
        """測試開始測驗狀態轉換"""
        mock_doc = {
            "session_id": "test-123",
            "mode": "color_taste",
            "language": "zh",
            "step": "initial",
            "current_q_index": 0,
            "answers": {},
            "current_question": None,
            "selected_questions": None,
            "chat_history": [],
            "color_result_id": None,
            "color_scores": {},
            "color_result": None,
            "quiz_id": "color_taste",
            "updated_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=30)
        }

        self.mock_sessions.find_one.return_value = mock_doc
        self.mock_sessions.update_one.return_value = MagicMock(matched_count=1)

        questions = [{"id": "q1"}, {"id": "q2"}]
        session = self.manager.start_quiz("test-123", questions)

        # 驗證
        self.assertIsNotNone(session)
        self.assertEqual(session.step, SessionStep.QUIZ)
        self.assertEqual(session.current_q_index, 0)
        self.assertEqual(session.answers, {})
        self.assertEqual(session.selected_questions, questions)

    def test_submit_answer(self):
        """測試提交答案"""
        mock_doc = {
            "session_id": "test-123",
            "mode": "color_taste",
            "language": "zh",
            "step": "quiz",
            "current_q_index": 0,
            "answers": {},
            "current_question": None,
            "selected_questions": None,
            "chat_history": [],
            "color_result_id": None,
            "color_scores": {},
            "color_result": None,
            "quiz_id": "color_taste",
            "updated_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=30)
        }

        self.mock_sessions.find_one.return_value = mock_doc
        self.mock_sessions.update_one.return_value = MagicMock(matched_count=1)

        session = self.manager.submit_answer("test-123", "q1", "a")

        # 驗證
        self.assertIsNotNone(session)
        self.assertEqual(session.answers, {"q1": "a"})
        self.assertEqual(session.current_q_index, 1)

    def test_clear_expired_sessions(self):
        """測試清理過期 sessions"""
        mock_result = MagicMock()
        mock_result.deleted_count = 5
        self.mock_sessions.delete_many.return_value = mock_result

        count = self.manager.clear_expired_sessions()

        # 驗證
        self.assertEqual(count, 5)
        self.mock_sessions.delete_many.assert_called_once()

    def test_get_sessions_by_mode(self):
        """測試按模式查詢 sessions"""
        mock_docs = [
            {
                "session_id": "test-1",
                "mode": "color_taste",
                "language": "zh",
                "step": "initial",
                "current_q_index": 0,
                "answers": {},
                "current_question": None,
                "selected_questions": None,
                "chat_history": [],
                "color_result_id": None,
                "color_scores": {},
                "color_result": None,
                "quiz_id": "color_taste",
                "updated_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(minutes=30),
                "_id": "id1"
            }
        ]

        self.mock_sessions.find.return_value = mock_docs

        sessions = self.manager.get_sessions_by_mode(GameMode.COLOR)

        # 驗證
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].session_id, "test-1")

    def test_get_statistics(self):
        """測試統計功能"""
        self.mock_sessions.count_documents.side_effect = [10, 5]  # 總數，完成數
        self.mock_sessions.aggregate.side_effect = [
            [{"_id": "color_taste", "count": 10}],  # mode stats
            [{"_id": "done", "count": 5}]  # step stats
        ]

        stats = self.manager.get_statistics()

        # 驗證
        self.assertEqual(stats["total_sessions"], 10)
        self.assertEqual(stats["completed_quizzes"], 5)


if __name__ == "__main__":
    unittest.main()
