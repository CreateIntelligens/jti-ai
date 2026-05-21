import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import os
import sys

# Ensure app is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Mock dependencies
mock_embedding_service = MagicMock()
mock_lancedb_store = MagicMock()
mock_mongodb_backup = MagicMock()

from app.services.rag.document_service import DocumentRagService
from app.services.rag.backfill import BackfillService

class TestDocumentRagService(unittest.TestCase):
    def setUp(self):
        self.patchers = [
            patch("app.services.rag.backfill.get_embedding_service", return_value=mock_embedding_service),
            patch("app.services.rag.backfill.get_lancedb_store", return_value=mock_lancedb_store),
            patch("app.services.rag.backfill.get_mongodb_backup", return_value=mock_mongodb_backup),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        for mocked in (mock_embedding_service, mock_lancedb_store, mock_mongodb_backup):
            mocked.reset_mock()
            mocked.side_effect = None

        mock_lancedb_store.get_file_fingerprint.return_value = None
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)

    def test_sync_txt_document_hciot(self):
        service = DocumentRagService()
        filename = "guidelines.txt"
        data = b"This is a long guideline text document that needs semantic chunking."

        service.sync_document(
            app="hciot",
            language="zh",
            filename=filename,
            data=data
        )

        # Check insertion into Vector Store
        mock_lancedb_store.insert_chunks.assert_called_once()
        inserted_records = mock_lancedb_store.insert_chunks.call_args[0][0]
        self.assertTrue(len(inserted_records) > 0)
        self.assertEqual(inserted_records[0]["source_type"], "hciot_doc_knowledge")
        self.assertEqual(inserted_records[0]["source_language"], "zh")
        self.assertEqual(inserted_records[0]["file_id"], filename)
        self.assertEqual(inserted_records[0]["metadata"]["path"], filename)

        # Check backup to MongoDB
        mock_mongodb_backup.sync_to_mongodb.assert_called_once()
        inserted_mongo_records = mock_mongodb_backup.sync_to_mongodb.call_args[0][0]
        self.assertEqual(inserted_mongo_records[0]["source_type"], "hciot_doc_knowledge")
        self.assertEqual(inserted_mongo_records[0]["source_language"], "zh")
        self.assertEqual(inserted_mongo_records[0]["file_id"], filename)

    def test_delete_document_hciot(self):
        service = DocumentRagService()
        filename = "guidelines.txt"

        service.delete_document(
            app="hciot",
            language="zh",
            filename=filename
        )

        mock_lancedb_store.delete_by_file.assert_called_once_with(
            filename,
            "hciot_doc_knowledge",
            source_language="zh"
        )
        mock_mongodb_backup.delete_by_file.assert_called_once_with(
            filename,
            "hciot_doc_knowledge"
        )

    @patch("app.routers.knowledge_utils.extract_docx_text")
    def test_backfill_docx_chunking(self, mock_extract_docx_text):
        mock_extract_docx_text.return_value = "Hello Paragraph 1\nHello Paragraph 2"

        backfill = BackfillService()
        
        # When force_text_chunking is True, it should use text chunking
        backfill.index_single_file(
            source_type="hciot_doc",
            language="zh",
            filename="instructions.docx",
            data=b"dummy docx binary",
            force_text_chunking=True
        )

        mock_lancedb_store.insert_chunks.assert_called_once()
        inserted_records = mock_lancedb_store.insert_chunks.call_args[0][0]
        self.assertEqual(inserted_records[0]["source_type"], "hciot_doc_knowledge")
        self.assertIn("Hello Paragraph 1", inserted_records[0]["text"])

if __name__ == "__main__":
    unittest.main()
