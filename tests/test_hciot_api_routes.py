import unittest
from tests.app_main_test_support import get_test_app


app = get_test_app()


class TestHciotApiRoutes(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
