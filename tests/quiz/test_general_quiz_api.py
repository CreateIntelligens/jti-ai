import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from tests.support.app_test_support import get_test_app, override_admin_auth

import sys
import importlib

app = get_test_app()


class TestGeneralQuizApi(unittest.TestCase):
    _original_modules = {}

    @classmethod
    def setUpClass(cls):
        # Backup original module references before mocks run
        for mod in ["app.services.mongo_client", "app.services.tts_jobs", "app.deps"]:
            if mod in sys.modules:
                cls._original_modules[mod] = sys.modules[mod]

    @classmethod
    def tearDownClass(cls):
        # Restore original modules in sys.modules
        for mod in ["app.services.mongo_client", "app.services.tts_jobs"]:
            if mod in sys.modules:
                del sys.modules[mod]

        for mod, module_ref in cls._original_modules.items():
            sys.modules[mod] = module_ref

        if "app.services.mongo_client" not in sys.modules:
            importlib.import_module("app.services.mongo_client")

        # Reload all modules to propagate the restored real client
        for mod in [
            "app.deps",
            "app.services.jti.quiz_bank_store",
            "app.services.jti.quiz_results_store",
            "app.tools.jti.tool_executor",
            "app.services.jti.runtime_quiz_flow",
            "app.services.jti.quiz_helpers",
            "app.routers.general.chat",
        ]:
            if mod in sys.modules:
                importlib.reload(sys.modules[mod])

    def setUp(self):
        self.cleanup_auth = override_admin_auth(app)
        from app.auth import verify_authenticated
        app.dependency_overrides[verify_authenticated] = lambda: {"role": "admin", "store_name": None}
        self.client = TestClient(app)

    def tearDown(self):
        self.cleanup_auth()
        from app.auth import verify_authenticated
        app.dependency_overrides.pop(verify_authenticated, None)

    @patch("app.deps.prompt_manager")
    def test_get_quiz_config_returns_data(self, mock_prompt_manager):
        mock_prompts = MagicMock()
        mock_prompts.quiz_enabled = True
        mock_prompts.quiz_start_keywords = ["test"]
        mock_prompts.quiz_negative_keywords = ["no"]
        mock_prompts.quiz_copy = {"zh": {"title": "Test"}}
        mock_prompt_manager.get_store_prompts.return_value = mock_prompts

        response = self.client.get(
            "/api/stores/test_store/quiz-config",
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["quiz_enabled"])
        self.assertEqual(payload["quiz_start_keywords"], ["test"])

    @patch("app.deps.prompt_manager")
    def test_put_quiz_config_saves_data(self, mock_prompt_manager):
        mock_prompts = MagicMock()
        mock_prompt_manager.get_store_prompts.return_value = mock_prompts

        response = self.client.put(
            "/api/stores/test_store/quiz-config",
            json={
                "quiz_enabled": True,
                "quiz_start_keywords": ["start"],
            },
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Quiz 設定已更新"})
        self.assertTrue(mock_prompts.quiz_enabled)
        self.assertEqual(mock_prompts.quiz_start_keywords, ["start"])
        mock_prompt_manager.save_store_prompts.assert_called_once_with(mock_prompts)

    @patch("app.routers.general.quiz_bank.get_quiz_bank_store")
    def test_list_banks_calls_store(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.list_banks.return_value = [{"name": "Bank 1"}]
        mock_get_store.return_value = mock_store

        response = self.client.get(
            "/api/general/quiz-bank/test_store/banks/",
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["banks"], [{"name": "Bank 1"}])
        mock_store.list_banks.assert_called_once_with("zh", store_name="test_store")

    @patch("app.deps.prompt_manager")
    @patch("app.routers.general.chat._get_session_manager")
    @patch("app.routers.general.chat.main_agent")
    @patch("app.services.jti.runtime_quiz_flow.ToolExecutor")
    def test_general_chat_message_triggers_quiz_start(
        self, mock_executor_cls, mock_agent, mock_get_session_mgr, mock_prompt_manager
    ):
        mock_prompts = MagicMock()
        mock_prompts.quiz_enabled = True
        mock_prompts.quiz_start_keywords = ["測驗"]
        mock_prompts.quiz_negative_keywords = ["不要"]
        mock_prompts.quiz_copy = {}
        mock_prompt_manager.get_store_prompts.return_value = mock_prompts

        # Mock Session
        mock_session = MagicMock()
        from app.models.session import SessionStep
        mock_session.step = SessionStep.WELCOME
        mock_session.language = "zh"
        mock_session.session_id = "test-session"
        mock_session.metadata = {"store_name": "test_store"}

        mock_session_mgr = MagicMock()
        mock_session_mgr.get_session.return_value = mock_session
        mock_get_session_mgr.return_value = mock_session_mgr

        # Mock ToolExecutor response
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "success": True,
            "current_question": {
                "id": "q1",
                "text": "First Question?",
                "options": [{"id": "a", "text": "Option A"}]
            }
        })
        mock_executor_cls.return_value = mock_executor

        # Mock main_agent session creation if needed
        mock_agent.create_session.return_value = mock_session

        response = self.client.post(
            "/api/chat/message",
            json={
                "message": "我要測驗",
                "session_id": "test-session"
            },
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("First Question?", payload["answer"])
        self.assertEqual(payload["options"], ["A. Option A"])


if __name__ == "__main__":
    unittest.main()

