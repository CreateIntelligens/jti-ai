import unittest
from tests.app_main_test_support import get_test_app


app = get_test_app()


class TestJtiApiRoutes(unittest.TestCase):
    def test_runtime_and_admin_routes_are_registered(self):
        routes = {
            (route.path, tuple(sorted(route.methods - {"HEAD", "OPTIONS"})))
            for route in app.routes
            if hasattr(route, "methods")
        }

        expected = {
            ("/api/jti/chat/start", ("POST",)),
            ("/api/jti/chat/message", ("POST",)),
            ("/api/jti/tts", ("POST",)),
            ("/api/jti/tts/{tts_message_id}", ("GET",)),
            ("/api/jti/quiz/start", ("POST",)),
            ("/api/jti/quiz/pause", ("POST",)),
            ("/api/jti-admin/conversations", ("DELETE",)),
            ("/api/jti-admin/conversations", ("GET",)),
            ("/api/jti-admin/conversations/export", ("GET",)),
            ("/api/jti-admin/prompts/", ("GET",)),
            ("/api/jti-admin/knowledge/files/", ("GET",)),
            ("/api/jti-admin/quiz-bank/banks/", ("GET",)),
            ("/api/knowledge/files/", ("GET",)),
        }

        for route in expected:
            self.assertIn(route, routes)

    def test_legacy_admin_compatibility_routes_still_exist(self):
        paths = {
            route.path
            for route in app.routes
            if hasattr(route, "methods")
        }

        self.assertIn("/api/jti/history", paths)
        self.assertIn("/api/jti/prompts/", paths)
        self.assertIn("/api/jti/knowledge/files/", paths)
        self.assertIn("/api/jti/quiz-bank/banks/", paths)


if __name__ == "__main__":
    unittest.main()
