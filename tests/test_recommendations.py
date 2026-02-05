import unittest

from app.models.session import Session, SessionStep
from app.services.session_manager import session_manager
from app.tools.tool_executor import tool_executor


class SessionModelTests(unittest.TestCase):
    def test_session_dump_includes_color_result(self):
        session = Session()
        data = session.model_dump()
        self.assertIn("color_result_id", data)
        self.assertIn("color_scores", data)


class ColorResultFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_calculate_color_result_after_scoring(self):
        session = session_manager.create_session()
        session_manager.start_scoring(session.session_id)
        session.answers = {"c1": "a", "c2": "b"}
        session_manager.update_session(session)

        result = await tool_executor.execute(
            "calculate_color_result",
            {"session_id": session.session_id}
        )
        self.assertEqual(result.get("color_id"), "metal")

        updated = session_manager.get_session(session.session_id)
        self.assertEqual(updated.step, SessionStep.DONE)
        self.assertEqual(updated.color_result_id, "metal")
