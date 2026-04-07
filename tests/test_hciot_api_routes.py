import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from tests.app_main_test_support import get_test_app


app = get_test_app()


class TestHciotApiRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_hciot_runtime_and_admin_routes_are_registered(self):
        routes = {
            (route.path, tuple(sorted(route.methods - {"HEAD", "OPTIONS"})))
            for route in app.routes
            if hasattr(route, "methods")
        }

        expected = {
            ("/api/hciot/chat/start", ("POST",)),
            ("/api/hciot/chat/message", ("POST",)),
            ("/api/hciot-admin/prompts/", ("GET",)),
            ("/api/hciot-admin/knowledge/files/", ("GET",)),
            ("/api/hciot-admin/knowledge/files/{filename}/metadata", ("PUT",)),
            ("/api/hciot-admin/conversations", ("GET",)),
            ("/api/hciot-admin/conversations/export", ("GET",)),
        }

        for route in expected:
            self.assertIn(route, routes)

    def test_hciot_compatibility_routes_exist(self):
        paths = {
            route.path
            for route in app.routes
            if hasattr(route, "methods")
        }

        self.assertIn("/api/hciot/history", paths)
        self.assertIn("/api/hciot/prompts/", paths)
        self.assertIn("/api/hciot/knowledge/files/", paths)

    def test_hciot_tts_characters_route_returns_character_list(self):
        response = self.client.get(
            "/api/hciot/tts/characters",
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("characters", payload)
        self.assertIsInstance(payload["characters"], list)
        self.assertGreater(len(payload["characters"]), 0)

    def test_hciot_chat_uses_request_tts_character_for_queued_audio(self):
        session = SimpleNamespace(language="zh")

        with (
            patch("app.routers.hciot.chat.session_manager.get_session", side_effect=[session, session]),
            patch("app.routers.hciot.chat.main_agent.chat", new=AsyncMock(return_value={"message": "您好"})),
            patch("app.routers.hciot.chat.conversation_logger.log_conversation", return_value=("log", 1)),
            patch(
                "app.routers.hciot.chat.attach_tts_message_id",
                side_effect=lambda response, language, manager, character=None: response,
            ) as attach_tts,
        ):
            response = self.client.post(
                "/api/hciot/chat/message",
                json={
                    "session_id": "session-1",
                    "message": "哈囉",
                    "tts_character": "healthy3",
                },
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(attach_tts.call_args.kwargs["character"], "healthy3")


if __name__ == "__main__":
    unittest.main()
