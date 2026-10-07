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

        # backfill 取 ESG store 用的是 app.services.rag.backfill.get_esg_knowledge_store
        # （見 backfill.py L276），須 patch 使用端；patch 錯模組會讓它讀到真實 ESG 資料。
        with patch(
            "app.services.rag.backfill.get_esg_knowledge_store",
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
        # 文件向量的標題用 topic，不用檔名
        self.assertEqual(
            mock_embedding_service.encode.call_args.kwargs["titles"],
            ["FAQ / Department Introductions"],
        )

    def test_upload_path_uses_same_topic_title_as_backfill(self):
        """KB 上傳/編輯不帶 topic_info；必須查回同一份 doc，否則向量跟全量重建不同。"""
        backfill = BackfillService()
        mock_embedding_service.encode.reset_mock()
        mock_embedding_service.encode.return_value = np.random.rand(1, 768)
        store = MagicMock()
        store.get_file.return_value = {
            "topic_label": "常見問題",
            "category_label": "常見問題",
        }

        with patch("app.services.rag.backfill.get_jti_knowledge_store", return_value=store):
            backfill.index_single_file("jti", "zh", "jti_001.csv", b"q,a\nQ?,A")

        store.get_file.assert_called_once_with("zh", "jti_001.csv")
        self.assertEqual(
            mock_embedding_service.encode.call_args.kwargs["titles"], ["常見問題"]
        )

    def test_general_upload_falls_back_to_legacy_store_for_topic(self):
        new_store = MagicMock()
        new_store.get_file.return_value = None
        old_store = MagicMock()
        old_store.get_file.return_value = {"topic_label": "釣點", "category_label": "台北"}

        with (
            patch("app.services.rag.backfill.get_general_knowledge_store", return_value=new_store),
            patch("app.services.rag.backfill.get_knowledge_store", return_value=old_store),
        ):
            info = BackfillService._fetch_topic_info("general", "store_x", "a.csv")

        old_store.get_file.assert_called_once_with("store_x", "a.csv", namespace="general")
        self.assertEqual(BackfillService._build_title(info), "台北 / 釣點")

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

    def test_plain_app_same_category_and_topic_yields_no_prefix(self):
        """JTI/ESG 的假 topic（category 與 topic 同名）不該產生前綴。"""
        for label in ("常見問題", "FAQ"):
            with self.subTest(label=label):
                prefix = BackfillService._build_topic_prefix(
                    {"category_label": label, "topic_label": label}
                )
                self.assertEqual(prefix, "")

    def test_distinct_category_and_topic_still_prefixed(self):
        """HCIoT 的真實分類仍要帶前綴。"""
        prefix = BackfillService._build_topic_prefix(
            {"category_label": "骨科", "topic_label": "痛風"}
        )
        self.assertEqual(prefix, "【骨科 / 痛風】")

    def test_title_uses_topic_even_without_prefix(self):
        """JTI/ESG 的假 topic 不加前綴，但仍可當標題；沒有 topic 就不給標題。"""
        cases = [
            ({"category_label": "常見問題", "topic_label": "常見問題"}, "常見問題"),
            ({"category_label": "骨科", "topic_label": "痛風"}, "骨科 / 痛風"),
            ({"category_label": "", "topic_label": ""}, ""),
        ]
        for topic_info, expected in cases:
            with self.subTest(topic_info=topic_info):
                self.assertEqual(BackfillService._build_title(topic_info), expected)

if __name__ == '__main__':
    unittest.main()
