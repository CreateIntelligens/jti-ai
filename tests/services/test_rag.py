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
mock_knowledge_store = MagicMock()

from app.services.rag.chunker import SemanticChunker
from app.services.rag.service import RAGPipeline
from app.services.rag.backfill import BackfillService

class TestRAGPipeline(unittest.TestCase):
    def setUp(self):
        self.patchers = [
            patch("app.services.rag.service.get_embedding_service", return_value=mock_embedding_service),
            patch("app.services.rag.service.get_lancedb_store", return_value=mock_lancedb_store),
            patch("app.services.rag.backfill.get_embedding_service", return_value=mock_embedding_service),
            patch("app.services.rag.backfill.get_lancedb_store", return_value=mock_lancedb_store),
            patch("app.services.rag.backfill.get_jti_knowledge_store", return_value=mock_knowledge_store),
            patch("app.services.rag.backfill.get_hciot_knowledge_store", return_value=mock_knowledge_store),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        for mocked in (mock_embedding_service, mock_lancedb_store, mock_knowledge_store):
            mocked.reset_mock()
            mocked.side_effect = None

        mock_lancedb_store.get_file_fingerprint.side_effect = None
        mock_lancedb_store.get_file_fingerprint.return_value = None
        mock_lancedb_store.get_all_fingerprints.side_effect = None
        mock_lancedb_store.get_all_fingerprints.return_value = {}
        mock_lancedb_store.search.side_effect = None
        mock_lancedb_store.search.return_value = []
        mock_knowledge_store.list_files.side_effect = None
        mock_knowledge_store.list_files.return_value = []
        mock_knowledge_store.list_files_with_data.side_effect = None
        mock_knowledge_store.list_files_with_data.return_value = []
        mock_knowledge_store.get_file_data.side_effect = None
        mock_knowledge_store.get_file_data.return_value = None

    def test_semantic_chunker(self):
        chunker = SemanticChunker(chunk_size_tokens=5)
        text = "This is a sentence. This is another one."
        chunks = chunker.chunk_text(text)
        # "This is a sentence." is ~5 tokens (19 chars / 4)
        self.assertTrue(len(chunks) >= 2)
        self.assertIn("This is a sentence.", chunks[0])

    def test_semantic_chunker_overlap(self):
        chunker = SemanticChunker(chunk_size_tokens=10, chunk_overlap_tokens=5)
        text = "First sentence. Second sentence. Third sentence."
        chunks = chunker.chunk_text(text)
        # With overlap, the last sentence(s) of chunk N should appear at the start of chunk N+1
        if len(chunks) >= 2:
            # Find overlap by checking if any sentence appears in consecutive chunks
            for i in range(len(chunks) - 1):
                words_current = set(chunks[i].split())
                words_next = set(chunks[i + 1].split())
                overlap = words_current & words_next
                self.assertTrue(len(overlap) > 0, "Chunks should overlap")

    def test_semantic_chunker_chinese(self):
        chunker = SemanticChunker(chunk_size_tokens=10, chunk_overlap_tokens=3)
        text = "這是第一句話。這是第二句話。這是第三句話。這是很長的第四句話需要更多空間。"
        chunks = chunker.chunk_text(text)
        # Chinese: 1 char ≈ 1 token, so 10 tokens ≈ 10 chars
        self.assertTrue(len(chunks) >= 2)

    def test_rag_pipeline_retrieve(self):
        pipeline = RAGPipeline()
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)
        mock_lancedb_store.search.return_value = [
            {"text": "found chunk", "metadata": {"path": "doc1.txt"}, "file_id": "doc1.txt", "_distance": 0.3}
        ]
        
        kb_text, citations = pipeline.retrieve("query text", language="zh", top_k=5)
        
        self.assertIn("found chunk", kb_text)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["uri"], "doc1.txt")

    def test_backfill_service(self):
        backfill = BackfillService()
        mock_knowledge_store.list_files_with_data.return_value = [
            {"filename": "test.txt", "display_name": "Test File", "data": b"some sample text data"}
        ]
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)

        backfill.run_backfill("jti", "zh")

        mock_lancedb_store.replace_file_chunks.assert_called_once()

    def test_backfill_batch_fingerprint_skip(self):
        """A file whose batch fingerprint matches is skipped without re-embedding."""
        backfill = BackfillService()
        data = b"some sample text data"
        fingerprint = backfill._compute_fingerprint(data)
        mock_knowledge_store.list_files_with_data.return_value = [
            {"filename": "test.txt", "display_name": "Test File", "data": data}
        ]
        # Batch map already has this file at the same fingerprint → unchanged.
        mock_lancedb_store.get_all_fingerprints.return_value = {"test.txt": fingerprint}
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)

        backfill.run_backfill("jti", "zh")

        # Skipped before the lock: no per-file fingerprint query, no embed, no write.
        mock_lancedb_store.replace_file_chunks.assert_not_called()
        mock_lancedb_store.get_file_fingerprint.assert_not_called()
        mock_embedding_service.encode.assert_not_called()

    def test_backfill_batch_fingerprint_changed_reindexes(self):
        """A file whose batch fingerprint differs is re-indexed (not skipped)."""
        backfill = BackfillService()
        mock_knowledge_store.list_files_with_data.return_value = [
            {"filename": "test.txt", "display_name": "Test File", "data": b"new content"}
        ]
        # Batch map has a stale fingerprint for this file → changed.
        mock_lancedb_store.get_all_fingerprints.return_value = {"test.txt": "stale-fp"}
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)

        backfill.run_backfill("jti", "zh")

        mock_lancedb_store.replace_file_chunks.assert_called_once()

    def test_general_backfill(self):
        backfill = BackfillService()
        new_store = MagicMock()
        old_store = MagicMock()

        new_store.list_files_with_data.return_value = [
            {"filename": "general_file.txt", "display_name": "General File", "data": b"general store text data"}
        ]
        old_store.list_files_with_data.return_value = []

        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)

        with patch("app.services.rag.backfill.get_knowledge_store", return_value=old_store), \
             patch("app.services.rag.backfill.get_general_knowledge_store", return_value=new_store):
            backfill.run_backfill("general", "store_123")

        mock_lancedb_store.replace_file_chunks.assert_called_once()
        new_store.list_files_with_data.assert_called_once_with("store_123")
        old_store.list_files_with_data.assert_called_once_with("store_123", namespace="general")

    def test_esg_backfill(self):
        backfill = BackfillService()
        esg_store = MagicMock()
        esg_store.list_files_with_data.return_value = [
            {"filename": "KIOSK_QA_中文.csv", "display_name": "ESG QA", "data": "q,a\nLED?,162 萬元".encode("utf-8")}
        ]

        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)

        with patch(
            "app.services.knowledge_store.get_namespaced_knowledge_store",
            return_value=esg_store,
        ):
            backfill.run_backfill("esg", "zh")

        mock_lancedb_store.replace_file_chunks.assert_called_once()
        # ESG must write under the esg_knowledge namespace so retrieval (which
        # routes managed_app="esg" → "esg_knowledge") can find it.
        self.assertEqual(
            mock_lancedb_store.replace_file_chunks.call_args.args[1], "esg_knowledge"
        )
        esg_store.list_files_with_data.assert_called_once_with("zh")

    def test_hciot_english_backfill_uses_topic_store_labels_for_prefix(self):
        backfill = BackfillService()
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)
        topic_store = MagicMock()
        topic_store.get_topic.return_value = {
            "labels": {"zh": "各科介紹", "en": "Department Introductions"},
            "category_labels": {"zh": "常見問題", "en": "FAQ"},
        }

        with patch("app.services.rag.backfill.get_hciot_topic_store", return_value=topic_store, create=True):
            backfill.index_single_file(
                source_type="hciot",
                language="en",
                filename="Department_Introductions.csv",
                data=b"q,a\nIntroduction?,Answer",
                topic_info={
                    "topic_id": "常見問題/各科介紹",
                    # Doc-level en labels missing — fall back to topic_store.
                    "topic_label": "",
                    "category_label": "",
                },
            )

        records = mock_lancedb_store.replace_file_chunks.call_args.args[3]
        self.assertTrue(records[0]["text"].startswith("【FAQ / Department Introductions】"))

    def test_hciot_backfill_skips_topic_store_lookup_when_labels_are_usable(self):
        topic_info = {
            "topic_id": "faq/department-introductions",
            "topic_label": "Department Introductions",
            "category_label": "FAQ",
        }

        with patch("app.services.rag.backfill.get_hciot_topic_store") as get_topic_store:
            result = BackfillService._merge_topic_store_labels("hciot", "en", topic_info)

        self.assertIs(result, topic_info)
        get_topic_store.assert_not_called()

if __name__ == '__main__':
    unittest.main()
