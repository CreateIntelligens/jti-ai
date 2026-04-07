import unittest

from app.models.session import Session, SessionStep
from app.services.session.session_manager_factory import get_session_manager

session_manager = get_session_manager()
from app.tools.jti.tool_executor import tool_executor


class SessionModelTests(unittest.TestCase):
    def test_session_dump_includes_quiz_result(self):
        session = Session()
        data = session.model_dump()
        self.assertIn("quiz_result_id", data)
        self.assertIn("quiz_scores", data)


class QuizResultFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_calculate_quiz_result_after_scoring(self):
        session = session_manager.create_session()
        session_manager.start_scoring(session.session_id)
        session.answers = {"q1": "a", "q2": "b"}
        session_manager.update_session(session)

        result = await tool_executor.execute(
            "calculate_quiz_result",
            {"session_id": session.session_id}
        )
        self.assertEqual(result.get("quiz_id"), "analyst")

        updated = session_manager.get_session(session.session_id)
        self.assertEqual(updated.step, SessionStep.DONE)
        self.assertEqual(updated.quiz_result_id, "analyst")

    async def test_calculate_quiz_result_uses_session_language(self):
        session = session_manager.create_session(language="en")
        session_manager.start_scoring(session.session_id)
        session.answers = {"q1": "a", "q2": "b"}
        session_manager.update_session(session)

        result = await tool_executor.execute(
            "calculate_quiz_result",
            {"session_id": session.session_id}
        )

        self.assertEqual(result.get("quiz_id"), "analyst")
        self.assertIn("You are Analyst", result.get("message", ""))
        self.assertNotIn("Maximize Every Moment", result.get("message", ""))
