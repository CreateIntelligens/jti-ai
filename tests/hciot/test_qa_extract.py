import unittest
from importlib.util import find_spec
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.auth import verify_admin, verify_auth
from tests.support.app_test_support import get_test_app


app = get_test_app()
app.dependency_overrides[verify_admin] = lambda: {"role": "admin"}
app.dependency_overrides[verify_auth] = lambda: {"role": "admin"}


class TestHciotQaExtractRemoved(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_ai_extraction_modules_are_removed(self):
        self.assertIsNone(find_spec("app.routers.hciot.qa_extract"))
        self.assertIsNone(find_spec("app.services.hciot.qa_extractor"))
        self.assertIsNone(find_spec("app.services.hciot.qa_extract_jobs"))
        self.assertIsNone(find_spec("app.services._shared.qa_kb.extractor_base"))
        self.assertIsNone(find_spec("app.services._shared.qa_kb.extract_jobs"))

    def test_qa_extract_endpoints_are_removed(self):
        endpoints = [
            ("post", "/api/hciot-admin/knowledge/qa-extract"),
            ("get", "/api/hciot-admin/knowledge/qa-extract/job-1"),
            ("post", "/api/hciot-admin/knowledge/qa-extract/job-1/import"),
            ("post", "/api/hciot/knowledge/qa-extract"),
            ("get", "/api/hciot/knowledge/qa-extract/job-1"),
            ("post", "/api/hciot/knowledge/qa-extract/job-1/import"),
        ]

        for method, path in endpoints:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 404)

    def test_upload_format_error_has_no_ai_fallback(self):
        fake_store = MagicMock()
        fake_topic_store = MagicMock()
        with patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
             patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
            response = self.client.post(
                "/api/hciot-admin/knowledge/upload/",
                data={
                    "category_id": "cat-1",
                    "topic_id": "topic-1",
                    "category_label": "Cat 1",
                    "topic_label": "Topic 1",
                    "language": "zh",
                },
                files={"file": ("malformed.csv", b"invalid headers\nrow1,row2", "text/csv")},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error_code"], "unrecognized_format")
        self.assertNotIn("can_fallback_to_ai", payload)
        self.assertIn("detail", payload)


if __name__ == "__main__":
    unittest.main()
