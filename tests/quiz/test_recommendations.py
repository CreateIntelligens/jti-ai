import unittest
from typing import Any

from app.models.session import Session

# Module-level globals rebound in QuizResultFlowTests.setUp. Do NOT eagerly build
# a real session manager or import tool_executor at module-import time — doing so
# creates real (non-mocked) singletons before other suites install their test
# mocks, which made HCIoT routes vanish (404) when this module imported first.
session_manager: Any = None
tool_executor: Any = None


class SessionModelTests(unittest.TestCase):
    def test_session_dump_includes_quiz_result(self):
        session = Session()
        data = session.model_dump()
        self.assertIn("quiz_result_id", data)
        self.assertIn("quiz_scores", data)


class QuizResultFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import sys
        import importlib

        # Snapshot app.* modules so tearDown can restore them. The forced reload
        # below is what aligns this test's session_manager and tool_executor to a
        # single fresh instance, but without restoration it leaks half-initialised
        # modules into later tests in the same process (cascading HCIoT failures).
        self._app_module_snapshot = {
            name: mod
            for name, mod in sys.modules.items()
            if name == "app" or name.startswith("app.")
        }

        # Unconditionally delete all app modules to force clean imports of everything
        for m in list(self._app_module_snapshot):
            del sys.modules[m]

        # Dynamically import models to get fresh class definitions matching the reloaded modules
        session_mod = importlib.import_module("app.models.session")
        self.Session = session_mod.Session
        self.SessionStep = session_mod.SessionStep

        sm_factory = importlib.import_module("app.services.session.session_manager_factory")
        if hasattr(sm_factory, "_singletons"):
            sm_factory._singletons.clear()

        global session_manager, tool_executor
        session_manager = sm_factory.get_jti_session_manager()
        
        tool_exec_mod = importlib.import_module("app.tools.jti.tool_executor")
        tool_executor = tool_exec_mod.tool_executor

        # Clear module-level caches in quiz and quiz_results tools
        quiz_mod = importlib.import_module("app.tools.jti.quiz")
        if hasattr(quiz_mod, "quiz_data_cache"):
            quiz_mod.quiz_data_cache.clear()
        results_mod = importlib.import_module("app.tools.jti.quiz_results")
        if hasattr(results_mod, "_quiz_results_cache"):
            results_mod._quiz_results_cache.clear()

    def tearDown(self):
        # Restore the pre-test app.* modules so this test's forced reload does not
        # leak rebuilt/half-initialised modules into later tests in the process.
        import sys

        for name in [
            n for n in sys.modules
            if n == "app" or n.startswith("app.")
        ]:
            del sys.modules[name]
        sys.modules.update(self._app_module_snapshot)

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
        self.assertEqual(updated.step, self.SessionStep.DONE)
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
