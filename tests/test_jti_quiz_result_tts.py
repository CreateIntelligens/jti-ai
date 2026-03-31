import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from tests.app_main_test_support import get_test_app


app = get_test_app()
from app.models.session import Session, SessionStep
from app.services.jti.tts_text import to_tts_text


class TestJtiQuizResultTts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_completed_quiz_prefers_tool_tts_text(self):
        initial_session = Session(
            session_id="session-1",
            step=SessionStep.QUIZ,
            language="zh",
            current_question={
                "id": "q1",
                "text": "你喜歡哪種旅行？",
                "options": [
                    {"id": "a", "text": "冒險"},
                    {"id": "b", "text": "放鬆"},
                ],
            },
            selected_questions=[{"id": "q1"}],
        )
        completed_session = Session(
            session_id="session-1",
            step=SessionStep.DONE,
            language="zh",
            answers={"q1": "a"},
            quiz_scores={"explorer": 1},
        )
        tool_result = {
            "is_complete": True,
            "message": "你是探險家，渴望冒險 探索每一刻驚喜。渴望冒險 探索每一刻驚喜，你總是勇於嘗試新鮮刺激的挑戰。",
            "tts_text": "你是探險家。渴望冒險 探索每一刻驚喜，你總是勇於嘗試新鮮刺激的挑戰。",
            "quiz_result": {"quiz_id": "explorer"},
        }

        with (
            patch("app.routers.jti.chat._get_or_rebuild_session", return_value=initial_session),
            patch("app.routers.jti.chat._judge_user_choice", new=AsyncMock(return_value="a")),
            patch("app.routers.jti.chat.get_total_questions", return_value=1),
            patch("app.routers.jti.chat.session_manager.get_session", return_value=completed_session),
            patch("app.routers.jti.chat.session_manager.update_session", return_value=completed_session),
            patch("app.routers.jti.chat.conversation_logger.log_conversation", return_value=("log", 1)),
            patch("app.routers.jti.chat.main_agent.remove_session"),
            patch("app.routers.jti.chat.attach_tts_message_id", side_effect=lambda response, language, manager: response),
            patch("app.tools.jti.tool_executor.tool_executor.execute", new=AsyncMock(return_value=tool_result)),
        ):
            response = self.client.post(
                "/api/jti/chat/message",
                json={"session_id": "session-1", "message": "A"},
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], tool_result["message"])
        self.assertEqual(payload["tts_text"], to_tts_text(tool_result["tts_text"], "zh"))


if __name__ == "__main__":
    unittest.main()
