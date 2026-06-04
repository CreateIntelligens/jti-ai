import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import os
import sys

# Ensure app is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Mock lancedb and pandas before imports
mock_lancedb = MagicMock()
sys.modules['lancedb'] = mock_lancedb
sys.modules['pandas'] = MagicMock()

import app.services.vector_store.lancedb as lancedb_module
from app.services.vector_store.lancedb import LanceDBStore

class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.lancedb_patcher = patch.object(lancedb_module, "lancedb", mock_lancedb)
        self.lancedb_patcher.start()
        self.addCleanup(self.lancedb_patcher.stop)
        mock_lancedb.reset_mock()

    def test_lancedb_insert_and_search(self):
        mock_db = MagicMock()
        mock_lancedb.connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = ["knowledge"]
        mock_table = MagicMock()
        mock_db.open_table.return_value = mock_table
        
        store = LanceDBStore(uri="memory://", table_name="knowledge")
        
        # Test insert
        chunks = [
            {"text": "hello", "vector": [0.1]*1024, "file_id": "f1", "source_language": "zh", "chunk_index": 0},
        ]
        store.insert_chunks(chunks)
        mock_table.add.assert_called_once()
        
        # Test search
        mock_query = MagicMock()
        mock_table.search.return_value = mock_query
        mock_query.distance_type.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.to_list.return_value = [{"text": "hello"}]
        
        results = store.search(np.array([0.1]*1024), language="zh", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "hello")

if __name__ == '__main__':
    unittest.main()
