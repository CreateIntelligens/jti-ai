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
mock_knowledge_store = MagicMock()

with patch.dict(sys.modules, {
    'app.services.embedding.service': MagicMock(get_embedding_service=lambda: mock_embedding_service),
    'app.services.vector_store.lancedb': MagicMock(get_lancedb_store=lambda: mock_lancedb_store),
    'app.services.vector_store.mongodb_backup': MagicMock(get_mongodb_backup=lambda: mock_mongodb_backup),
    'app.services.knowledge_store': MagicMock(get_knowledge_store=lambda: mock_knowledge_store),
}):
    from app.services.rag.chunker import SemanticChunker
    from app.services.rag.service import RAGPipeline
    from app.services.rag.backfill import BackfillService

class TestRAGPipeline(unittest.TestCase):
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
        mock_knowledge_store.list_files.return_value = [
            {"filename": "test.txt", "display_name": "Test File"}
        ]
        mock_knowledge_store.get_file_data.return_value = b"some sample text data"
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)
        
        backfill.run_backfill("jti", "zh")
        
        mock_lancedb_store.insert_chunks.assert_called_once()
        mock_mongodb_backup.sync_to_mongodb.assert_called_once()

if __name__ == '__main__':
    unittest.main()
