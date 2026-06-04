import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.auth import verify_admin, verify_auth
from tests.support.app_test_support import get_test_app
from app.services.hciot.qa_extract_jobs import _JOBS

app = get_test_app()
app.dependency_overrides[verify_admin] = lambda: {"role": "admin"}
app.dependency_overrides[verify_auth] = lambda: {"role": "admin"}


class TestHciotQaExtract(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _JOBS.clear()

    def test_qa_extract_text_removed(self):
        # /qa-extract/text endpoint should be removed (404)
        response = self.client.post(
            "/api/hciot-admin/knowledge/qa-extract/text",
            json={
                "text": "some text",
                "category_id": "cat-1",
                "topic_id": "topic-1",
                "category_label": "Cat 1",
                "topic_label": "Topic 1",
            }
        )
        self.assertIn(response.status_code, (404, 405))

    @patch("app.routers.hciot.qa_extract._run_extract_job_from_text")
    def test_qa_extract_docx(self, mock_bg_task):
        with patch("app.routers.hciot.qa_extract.extract_docx_text", return_value="hello docx content"):
            response = self.client.post(
                "/api/hciot-admin/knowledge/qa-extract",
                data={
                    "category_id": "cat-1",
                    "topic_id": "topic-1",
                    "category_label": "Cat 1",
                    "topic_label": "Topic 1",
                    "language": "zh",
                },
                files={"file": ("test.docx", b"dummy docx bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("job_id", payload)
            self.assertEqual(payload["status"], "pending")
            self.assertTrue(len(_JOBS) > 0)

    @patch("app.routers.hciot.qa_extract._run_extract_job_from_text")
    def test_qa_extract_csv_utf8(self, mock_bg_task):
        response = self.client.post(
            "/api/hciot-admin/knowledge/qa-extract",
            data={
                "category_id": "cat-1",
                "topic_id": "topic-1",
                "category_label": "Cat 1",
                "topic_label": "Topic 1",
                "language": "zh",
            },
            files={"file": ("test.csv", b"q,a\nhello question,hello answer", "text/csv")}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("job_id", payload)
        self.assertEqual(payload["status"], "pending")

    @patch("app.routers.hciot.qa_extract._run_extract_job_from_text")
    def test_qa_extract_xlsx(self, mock_bg_task):
        with patch("app.routers.hciot.qa_extract.xlsx_to_csv_bytes", return_value=b"q,a\nxlsx question,xlsx answer"):
            response = self.client.post(
                "/api/hciot-admin/knowledge/qa-extract",
                data={
                    "category_id": "cat-1",
                    "topic_id": "topic-1",
                    "category_label": "Cat 1",
                    "topic_label": "Topic 1",
                    "language": "zh",
                },
                files={"file": ("test.xlsx", b"dummy xlsx bytes", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("job_id", payload)
            self.assertEqual(payload["status"], "pending")

    def test_qa_extract_too_long(self):
        long_text = "a" * 30001
        response = self.client.post(
            "/api/hciot-admin/knowledge/qa-extract",
            data={
                "category_id": "cat-1",
                "topic_id": "topic-1",
                "category_label": "Cat 1",
                "topic_label": "Topic 1",
                "language": "zh",
            },
            files={"file": ("test.txt", long_text.encode("utf-8"), "text/plain")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "text_too_long")

    def test_upload_fallback_structured_error(self):
        fake_store = MagicMock()
        fake_topic_store = MagicMock()
        with patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
             patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
            malformed_csv = b"invalid headers\nrow1,row2"
            response = self.client.post(
                "/api/hciot-admin/knowledge/upload/",
                data={
                    "category_id": "cat-1",
                    "topic_id": "topic-1",
                    "category_label": "Cat 1",
                    "topic_label": "Topic 1",
                    "language": "zh",
                },
                files={"file": ("malformed.csv", malformed_csv, "text/csv")}
            )
            self.assertEqual(response.status_code, 400)
            payload = response.json()
            self.assertEqual(payload["error_code"], "unrecognized_format")
            self.assertEqual(payload["can_fallback_to_ai"], True)
            self.assertIn("detail", payload)


class TestQaExtractorPromptCompilation(unittest.IsolatedAsyncioTestCase):
    def test_build_instruction_zh(self):
        from app.services.hciot.qa_extractor import _build_extraction_instruction

        persona = "我是醫院衛教助理小元"
        role_scope = "1. 回答與醫院衛教資料相關的問題"

        instruction = _build_extraction_instruction("zh", persona, role_scope)

        self.assertIn("我是醫院衛教助理小元", instruction)
        self.assertIn("1. 回答與醫院衛教資料相關的問題", instruction)
        self.assertIn("口語發問", instruction)
        self.assertIn("我該怎麼做", instruction)

    def test_build_instruction_en(self):
        from app.services.hciot.qa_extractor import _build_extraction_instruction

        persona = "I am a medical health assistant Xiaoyuan"
        role_scope = "1. Answer questions about medical topics"

        instruction = _build_extraction_instruction("en", persona, role_scope)

        self.assertIn("I am a medical health assistant Xiaoyuan", instruction)
        self.assertIn("1. Answer questions about medical topics", instruction)
        self.assertIn("Oral Questions", instruction)
        self.assertIn("What should I do", instruction)

    @patch("app.services.hciot.qa_extractor.get_default_client")
    @patch("app.services.hciot.qa_extractor.gemini_with_fallback")
    async def test_extract_qa_from_document_passes_persona_and_scope(self, mock_gemini_fallback, mock_get_client):
        from app.services.hciot.qa_extractor import extract_qa_from_document

        mock_response = MagicMock()
        mock_response.text = '{"qa_pairs": [{"q": "問題", "a": "答案"}]}'
        mock_gemini_fallback.return_value = mock_response

        res = await extract_qa_from_document("測試文字", "zh", "我是一般客服人員", "服務範圍說明")

        self.assertEqual(res, [{"q": "問題", "a": "答案"}])


if __name__ == "__main__":
    unittest.main()
