"""
Unit tests for rebuild_session_from_logs()

Tests:
1. Rebuild QUIZ state (mid-quiz with 2 answers)
2. Rebuild DONE state (completed quiz)
3. Rebuild paused quiz (WELCOME + partial answers)
4. Degrade when selected_questions incomplete
5. Empty logs returns None
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

# Mock MongoDB before any app imports
mock_db = MagicMock()
mock_mongo_client_module = MagicMock()
mock_mongo_client_module.get_mongo_db.return_value = mock_db
sys.modules.setdefault("app.services.mongo_client", mock_mongo_client_module)

from app.models.session import Session, SessionStep, GameMode
from app.services.session.mongo_session_manager import MongoSessionManager


def _make_question(qid: str, text: str = "Test question") -> dict:
    return {
        "id": qid,
        "text": text,
        "options": [
            {"id": f"{qid}_a", "text": "Option A"},
            {"id": f"{qid}_b", "text": "Option B"},
        ],
    }


def _make_log(
    session_id: str,
    turn: int,
    user_message: str,
    agent_response: str,
    tool_calls: list = None,
    snapshot_step: str = "WELCOME",
    answers_count: int = 0,
    color_result_id=None,
    current_question_id=None,
) -> dict:
    return {
        "session_id": session_id,
        "mode": "jti",
        "turn_number": turn,
        "user_message": user_message,
        "agent_response": agent_response,
        "tool_calls": tool_calls or [],
        "session_snapshot": {
            "step": snapshot_step,
            "answers_count": answers_count,
            "color_result_id": color_result_id,
            "current_question_id": current_question_id,
        },
    }


class TestRebuildSessionFromLogs(unittest.TestCase):
    """Tests for MongoSessionManager.rebuild_session_from_logs()"""

    def setUp(self):
        self.mock_sessions = MagicMock()
        mock_db.__getitem__.return_value = self.mock_sessions
        self.manager = MongoSessionManager()

    def test_empty_logs_returns_none(self):
        """Empty logs should return None"""
        result = self.manager.rebuild_session_from_logs("test-sid", [])
        self.assertIsNone(result)

    def test_rebuild_quiz_state(self):
        """Rebuild mid-quiz session: 2 answers completed, on question 3"""
        sid = "test-quiz-mid"
        q1 = _make_question("q1")
        q2 = _make_question("q2")
        q3 = _make_question("q3")

        logs = [
            # Turn 1: start_quiz
            _make_log(sid, 1, "開始測驗", "好的！第1題...",
                      tool_calls=[{
                          "tool": "start_quiz",
                          "args": {"session_id": sid},
                          "result": {"success": True, "current_question": q1},
                      }],
                      snapshot_step="QUIZ", answers_count=0, current_question_id="q1"),
            # Turn 2: answer q1 -> get q2
            _make_log(sid, 2, "A", "你選了A！第2題...",
                      tool_calls=[{
                          "tool": "submit_answer",
                          "args": {"user_choice": "A"},
                          "result": {
                              "success": True,
                              "answered": "q1",
                              "selected": "q1_a",
                              "current_index": 1,
                              "total_questions": 5,
                              "is_complete": False,
                              "next_question": q2,
                          },
                      }],
                      snapshot_step="QUIZ", answers_count=1, current_question_id="q2"),
            # Turn 3: answer q2 -> get q3
            _make_log(sid, 3, "B", "你選了B！第3題...",
                      tool_calls=[{
                          "tool": "submit_answer",
                          "args": {"user_choice": "B"},
                          "result": {
                              "success": True,
                              "answered": "q2",
                              "selected": "q2_b",
                              "current_index": 2,
                              "total_questions": 5,
                              "is_complete": False,
                              "next_question": q3,
                          },
                      }],
                      snapshot_step="QUIZ", answers_count=2, current_question_id="q3"),
        ]

        session = self.manager.rebuild_session_from_logs(sid, logs)

        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, sid)
        self.assertEqual(session.step, SessionStep.QUIZ)
        self.assertEqual(session.answers, {"q1": "q1_a", "q2": "q2_b"})
        self.assertEqual(session.current_q_index, 2)
        self.assertEqual(len(session.selected_questions), 3)     # q1, q2, q3
        self.assertEqual(session.current_question["id"], "q3")   # next question
        self.assertEqual(len(session.chat_history), 6)            # 3 turns x 2
        self.mock_sessions.update_one.assert_called_once()

    def test_rebuild_done_state(self):
        """Rebuild completed quiz session with color result"""
        sid = "test-done"
        q1 = _make_question("q1")

        logs = [
            _make_log(sid, 1, "開始測驗", "好的！",
                      tool_calls=[{
                          "tool": "start_quiz",
                          "args": {},
                          "result": {"success": True, "current_question": q1},
                      }],
                      snapshot_step="QUIZ"),
            # Final answer with color_result
            _make_log(sid, 2, "A", "恭喜完成！你的色系是...",
                      tool_calls=[{
                          "tool": "submit_answer",
                          "args": {"user_choice": "A"},
                          "result": {
                              "success": True,
                              "answered": "q1",
                              "selected": "q1_a",
                              "is_complete": True,
                              "color_result": {
                                  "color_scores": {"warm": 3, "cool": 2},
                                  "result": {"name": "暖色系", "description": "..."},
                              },
                          },
                      }],
                      snapshot_step="DONE", answers_count=1, color_result_id="warm"),
        ]

        session = self.manager.rebuild_session_from_logs(sid, logs)

        self.assertIsNotNone(session)
        self.assertEqual(session.step, SessionStep.DONE)
        self.assertEqual(session.color_result_id, "warm")
        self.assertEqual(session.color_scores, {"warm": 3, "cool": 2})
        self.assertIsNotNone(session.color_result)
        self.assertIsNone(session.current_question)

    def test_rebuild_paused_quiz(self):
        """Rebuild paused quiz: WELCOME step + partial answers -> paused_quiz=True"""
        sid = "test-paused"
        q1 = _make_question("q1")
        q2 = _make_question("q2")

        logs = [
            _make_log(sid, 1, "開始測驗", "好的！",
                      tool_calls=[{
                          "tool": "start_quiz",
                          "args": {},
                          "result": {"success": True, "current_question": q1},
                      }],
                      snapshot_step="QUIZ"),
            _make_log(sid, 2, "A", "好的！第2題...",
                      tool_calls=[{
                          "tool": "submit_answer",
                          "args": {"user_choice": "A"},
                          "result": {
                              "success": True,
                              "answered": "q1",
                              "selected": "q1_a",
                              "is_complete": False,
                              "next_question": q2,
                          },
                      }],
                      snapshot_step="QUIZ", answers_count=1),
            # Paused: step reverts to WELCOME
            _make_log(sid, 3, "中斷", "好的，先暫停。",
                      snapshot_step="WELCOME", answers_count=1),
        ]

        session = self.manager.rebuild_session_from_logs(sid, logs)

        self.assertIsNotNone(session)
        self.assertEqual(session.step, SessionStep.WELCOME)
        self.assertEqual(len(session.answers), 1)
        self.assertTrue(session.metadata.get("paused_quiz"))

    def test_degrade_missing_questions(self):
        """When step=QUIZ but no selected_questions, degrade to WELCOME"""
        sid = "test-degrade"

        logs = [
            # A log with QUIZ step but no start_quiz tool_call
            _make_log(sid, 1, "hi", "hello",
                      snapshot_step="QUIZ"),
        ]

        session = self.manager.rebuild_session_from_logs(sid, logs)

        self.assertIsNotNone(session)
        # Should degrade to WELCOME because no selected_questions
        self.assertEqual(session.step, SessionStep.WELCOME)

    def test_chat_history_built_correctly(self):
        """Chat history should include all user/agent message pairs"""
        sid = "test-history"

        logs = [
            _make_log(sid, 1, "hello", "嗨！歡迎！"),
            _make_log(sid, 2, "你好", "有什麼需要幫助的嗎？"),
        ]

        session = self.manager.rebuild_session_from_logs(sid, logs)

        self.assertEqual(len(session.chat_history), 4)
        self.assertEqual(session.chat_history[0], {"role": "user", "content": "hello"})
        self.assertEqual(session.chat_history[1], {"role": "assistant", "content": "嗨！歡迎！"})
        self.assertEqual(session.chat_history[2], {"role": "user", "content": "你好"})
        self.assertEqual(session.chat_history[3], {"role": "assistant", "content": "有什麼需要幫助的嗎？"})


if __name__ == "__main__":
    unittest.main()
