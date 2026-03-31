import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from tests.app_main_test_support import get_test_app


app = get_test_app()


class TestJtiKnowledgeCoreValidation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_upload_rejects_core_marker_in_text_files(self):
        store = MagicMock()

        with patch("app.routers.jti.knowledge.get_knowledge_store", return_value=store):
            response = self.client.post(
                "/api/jti-admin/knowledge/upload/?language=zh",
                files={"file": ("guide.csv", BytesIO(b"[CORE: secret]"), "text/csv")},
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("[CORE:", response.json()["detail"])
        store.insert_file.assert_not_called()

    def test_update_rejects_core_marker_in_text_content(self):
        store = MagicMock()
        store.get_file.return_value = {
            "filename": "guide.csv",
            "data": b"old",
        }

        with patch("app.routers.jti.knowledge.get_knowledge_store", return_value=store):
            response = self.client.put(
                "/api/jti-admin/knowledge/files/guide.csv/content?language=zh",
                json={"content": "[CORE: secret]"},
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("[CORE:", response.json()["detail"])
        store.update_file_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
