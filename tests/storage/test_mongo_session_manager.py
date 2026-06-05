"""
MongoDB SessionManager 單元測試

測試項目：
1. CRUD 操作
2. 狀態轉換
3. 查詢功能
"""

import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from app.models.session import Session, SessionStep


class TestMongoSessionManager(unittest.TestCase):
    """MongoDB SessionManager 測試"""

    @patch("app.services.session.mongo_session_manager.get_mongo_db")
    def setUp(self, mock_get_db):
        """測試前準備"""
        self.mock_db = MagicMock()
        mock_get_db.return_value = self.mock_db

        # 模擬 sessions 集合
        self.mock_sessions = MagicMock()
        self.mock_db.__getitem__.return_value = self.mock_sessions

        from app.services.session.mongo_session_manager import MongoSessionManager
        self.manager = MongoSessionManager(db_name="jti_app")

    def _make_valid_mock_doc(self, **overrides):
        """建立有效的 mock document（使用正確的 enum 值）"""
        doc = {
            "session_id": "test-123",
            "mode": "COLOR",
            "language": "zh",
            "step": "WELCOME",
            "current_q_index": 0,
            "answers": {},
            "current_question": None,
            "selected_questions": None,
            "chat_history": [],
            "quiz_result_id": None,
            "quiz_scores": {},
            "quiz_result": None,
            "quiz_id": "color_taste",
            "updated_at": datetime.now().isoformat(),
        }
        doc.update(overrides)
        return doc

    def test_create_session_is_lazy(self):
        """測試建立 session 為 lazy：不立即落庫，僅暫存於 _pending。

        為避免開頁/重整即產生空 WELCOME session 積壓，create_session 不再
        寫入 MongoDB，而是把 session 放進 _pending，待首則真實訊息經
        update_session 才 flush 落庫。
        """
        session = self.manager.create_session(language="zh")

        self.assertIsNotNone(session)
        self.assertEqual(session.language, "zh")
        self.assertEqual(session.step, SessionStep.WELCOME)
        # 不應寫入 DB
        self.mock_sessions.update_one.assert_not_called()
        # 應暫存於 _pending，且可由 get_session 讀回（不查 DB）
        self.assertIn(session.session_id, self.manager._pending)
        fetched = self.manager.get_session(session.session_id)
        self.assertIs(fetched, session)
        self.mock_sessions.find_one.assert_not_called()

    def test_update_session_flushes_pending_with_expires_at(self):
        """測試 update_session 會 flush pending session 並寫入動態 expires_at。"""
        session = self.manager.create_session(language="zh")
        self.mock_sessions.update_one.return_value = MagicMock(matched_count=1)

        self.manager.update_session(session)

        # 落庫後應從 _pending 移除
        self.assertNotIn(session.session_id, self.manager._pending)
        self.mock_sessions.update_one.assert_called_once()
        set_doc = self.mock_sessions.update_one.call_args.args[1]["$set"]
        self.assertIn("expires_at", set_doc)
        self.assertIsInstance(set_doc["expires_at"], datetime)
        # WELCOME 預設 3 天 TTL，過期時間應在未來
        self.assertGreater(set_doc["expires_at"], datetime.now())

    def test_get_session(self):
        """測試取得 session"""
        mock_doc = self._make_valid_mock_doc()
        self.mock_sessions.find_one.return_value = mock_doc

        session = self.manager.get_session("test-123")

        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, "test-123")
        self.mock_sessions.find_one.assert_called_once_with(
            {"session_id": "test-123"}
        )

    def test_get_session_not_found(self):
        """測試取得不存在的 session"""
        self.mock_sessions.find_one.return_value = None

        session = self.manager.get_session("nonexistent")

        self.assertIsNone(session)

    def test_update_session(self):
        """測試更新 session"""
        session = Session(language="zh")
        session.step = SessionStep.QUIZ

        mock_result = MagicMock()
        mock_result.matched_count = 1
        self.mock_sessions.update_one.return_value = mock_result

        updated = self.manager.update_session(session)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.step, SessionStep.QUIZ)
        self.mock_sessions.update_one.assert_called_once()

    def test_delete_session(self):
        """測試刪除 session"""
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        self.mock_sessions.delete_one.return_value = mock_result

        result = self.manager.delete_session("test-123")

        self.assertTrue(result)
        self.mock_sessions.delete_one.assert_called_once_with(
            {"session_id": "test-123"}
        )

    def test_start_quiz(self):
        """測試開始測驗狀態轉換"""
        mock_doc = self._make_valid_mock_doc()
        self.mock_sessions.find_one.return_value = mock_doc
        self.mock_sessions.update_one.return_value = MagicMock(matched_count=1)

        questions = [{"id": "q1"}, {"id": "q2"}]
        session = self.manager.start_quiz("test-123", questions)

        self.assertIsNotNone(session)
        self.assertEqual(session.step, SessionStep.QUIZ)
        self.assertEqual(session.current_q_index, 0)
        self.assertEqual(session.answers, {})
        self.assertEqual(session.selected_questions, questions)

    def test_submit_answer(self):
        """測試提交答案"""
        mock_doc = self._make_valid_mock_doc(step="QUIZ")
        self.mock_sessions.find_one.return_value = mock_doc
        self.mock_sessions.update_one.return_value = MagicMock(matched_count=1)

        session = self.manager.submit_answer("test-123", "q1", "a")

        self.assertIsNotNone(session)
        self.assertEqual(session.answers, {"q1": "a"})
        self.assertEqual(session.current_q_index, 1)

    def test_get_statistics(self):
        """測試統計功能"""
        self.mock_sessions.count_documents.side_effect = [10, 5]
        self.mock_sessions.aggregate.side_effect = [
            [{"_id": "COLOR", "count": 10}],
            [{"_id": "DONE", "count": 5}]
        ]

        stats = self.manager.get_statistics()

        self.assertEqual(stats["total_sessions"], 10)
        self.assertEqual(stats["completed_quizzes"], 5)


if __name__ == "__main__":
    unittest.main()
