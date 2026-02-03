import unittest

from app.models.session import Session, SessionStep
from app.services.session_manager import session_manager
from app.tools.tool_executor import tool_executor


class SessionModelTests(unittest.TestCase):
    def test_session_dump_includes_recommended_products(self):
        session = Session()
        data = session.model_dump()
        self.assertIn("recommended_products", data)


class RecommendationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_recommend_products_after_scoring(self):
        session = session_manager.create_session()
        session_manager.start_scoring(session.session_id)
        session_manager.complete_scoring(
            session.session_id,
            persona="INTJ",
            scores={}
        )
        updated = session_manager.get_session(session.session_id)
        self.assertEqual(updated.step, SessionStep.RECOMMEND)

        result = await tool_executor.execute(
            "recommend_products",
            {"session_id": session.session_id}
        )
        self.assertIn("message", result)
        self.assertTrue(result.get("products"))

        updated = session_manager.get_session(session.session_id)
        self.assertEqual(updated.step, SessionStep.DONE)
        self.assertTrue(updated.recommended_products)
