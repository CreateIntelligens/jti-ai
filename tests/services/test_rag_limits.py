import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.routers.knowledge_utils import (
    MAX_SINGLE_UPLOAD_SIZE_BYTES,
    SimpleRateLimiter,
    validate_upload_limits,
)
from app.services.rag.backfill import BackfillService


MB = 1024 * 1024


class TestRagLimitsAndPruning(unittest.TestCase):
    def test_simple_rate_limiter(self):
        limiter = SimpleRateLimiter(requests_limit=3, window_seconds=10)
        self.assertTrue(limiter.is_allowed("ip1"))
        self.assertTrue(limiter.is_allowed("ip1"))
        self.assertTrue(limiter.is_allowed("ip1"))
        self.assertFalse(limiter.is_allowed("ip1"))
        self.assertTrue(limiter.is_allowed("ip2"))

    def test_allowed_extensions_whitelist(self):
        files = []
        validate_upload_limits(files, "file.txt", b"hello")
        validate_upload_limits(files, "file.csv", b"hello")
        validate_upload_limits(files, "file.md", b"hello")
        validate_upload_limits(files, "file.docx", b"hello")
        validate_upload_limits(files, "file.xlsx", b"hello")

        for bad_ext in [".pdf", ".exe", ".png", ".zip"]:
            with self.assertRaises(HTTPException) as ctx:
                validate_upload_limits(files, f"file{bad_ext}", b"hello")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("不支援的檔案格式", ctx.exception.detail)

    def test_single_file_size_limit(self):
        large_bytes = b"x" * (MAX_SINGLE_UPLOAD_SIZE_BYTES + 1)
        files = []
        with self.assertRaises(HTTPException) as ctx:
            validate_upload_limits(files, "test_large.txt", large_bytes)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("單一檔案大小不可超過 5 MB", ctx.exception.detail)

    def test_total_file_count_limit(self):
        files = [{"filename": f"file_{i}.txt", "size": 100} for i in range(100)]
        with self.assertRaises(HTTPException) as ctx:
            validate_upload_limits(files, "new_file.txt", b"hello")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("數量已達上限", ctx.exception.detail)

        validate_upload_limits(files, "file_0.txt", b"hello")

    def test_total_size_limit(self):
        files = [
            {"filename": "file_1.txt", "size": 25 * MB},
            {"filename": "file_2.txt", "size": 22 * MB},
        ]
        with self.assertRaises(HTTPException) as ctx:
            validate_upload_limits(files, "file_3.txt", b"x" * (4 * MB))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("總容量已達上限", ctx.exception.detail)

        validate_upload_limits(files, "file_2.txt", b"x" * (4 * MB))

    @patch("app.services.rag.backfill.BackfillService.__init__", lambda x: None)
    def test_prune_test_orphans(self):
        service = BackfillService()
        service._lancedb_store = MagicMock()
        service.delete_from_rag = MagicMock()

        service.lancedb_store.list_file_ids.return_value = {
            "qa_1.txt", "test_2.txt", "QA254-4.txt", "normal_3.txt",
        }

        service._prune_test_orphans("hciot", "zh")

        self.assertEqual(service.delete_from_rag.call_count, 3)
        called_args = [call[0] for call in service.delete_from_rag.call_args_list]
        called_files = {arg[1] for arg in called_args}
        self.assertEqual(called_files, {"qa_1.txt", "test_2.txt", "QA254-4.txt"})
