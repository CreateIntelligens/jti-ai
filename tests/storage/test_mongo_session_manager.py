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

    def test_create_session_persists_immediately(self):
        """測試建立 session 即落庫（多 worker 共享狀態，取代舊 _pending lazy-write）。

        舊設計用 process 內 _pending 暫存，記憶體不跨 worker 導致 prod 多 worker
        失憶（/chat/start 與 /chat/message 打到不同 worker → 404）。改為建立即
        upsert 進 MongoDB，並寫入動態 expires_at 由 TTL 回收空 session。
        """
        session = self.manager.create_session(language="zh")

        self.assertIsNotNone(session)
        self.assertEqual(session.language, "zh")
        self.assertEqual(session.step, SessionStep.WELCOME)
        # 應立即 upsert 落庫
        self.mock_sessions.update_one.assert_called_once()
        call = self.mock_sessions.update_one.call_args
        self.assertEqual(call.args[0], {"session_id": session.session_id})
        self.assertTrue(call.kwargs.get("upsert"))
        set_doc = call.args[1]["$set"]
        self.assertIn("expires_at", set_doc)
        self.assertIsInstance(set_doc["expires_at"], datetime)
        self.assertGreater(set_doc["expires_at"], datetime.now())
        # 不應殘留 _pending 機制
        self.assertFalse(hasattr(self.manager, "_pending"))

    @patch("app.services.session.mongo_session_manager.get_mongo_db")
    def test_session_is_readable_across_workers(self, mock_get_db):
        """模擬跨 worker：A worker 建 session，B worker（不同實例、不共享記憶體）應讀得到。

        這是防 404 失憶的核心保證——狀態必須經 MongoDB 共享，而非 process 記憶體。
        """
        # 共用同一個 mock collection 模擬「同一個 MongoDB、不同 process」
        shared_db = MagicMock()
        shared_sessions = MagicMock()
        shared_db.__getitem__.return_value = shared_sessions
        mock_get_db.return_value = shared_db

        from app.services.session.mongo_session_manager import MongoSessionManager
        worker_a = MongoSessionManager(db_name="jti_app")
        worker_b = MongoSessionManager(db_name="jti_app")

        # worker A 建 session（落庫）
        session = worker_a.create_session(language="zh")
        persisted_doc = shared_sessions.update_one.call_args.args[1]["$set"]
        persisted_doc["session_id"] = session.session_id

        # worker B 透過 DB 讀回（模擬 DB 已有該文件）
        shared_sessions.find_one.return_value = persisted_doc
        fetched = worker_b.get_session(session.session_id)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.session_id, session.session_id)
        shared_sessions.find_one.assert_called_once_with(
            {"session_id": session.session_id}
        )

    def test_update_session_writes_expires_at(self):
        """測試 update_session 寫入動態 expires_at。"""
        session = self.manager.create_session(language="zh")
        self.mock_sessions.update_one.reset_mock()
        self.mock_sessions.update_one.return_value = MagicMock(matched_count=1)

        self.manager.update_session(session)

        self.mock_sessions.update_one.assert_called_once()
        set_doc = self.mock_sessions.update_one.call_args.args[1]["$set"]
        self.assertIn("expires_at", set_doc)
        self.assertIsInstance(set_doc["expires_at"], datetime)
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
