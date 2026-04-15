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

from app.services.vector_store.lancedb import LanceDBStore
from app.services.vector_store.mongodb_backup import MongoDBBackup

class TestVectorStore(unittest.TestCase):
    def test_lancedb_insert_and_search(self):
        mock_db = MagicMock()
        mock_lancedb.connect.return_value = mock_db
        mock_db.table_names.return_value = ["knowledge"]
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
        mock_query.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.to_list.return_value = [{"text": "hello"}]
        
        results = store.search(np.array([0.1]*1024), language="zh", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "hello")

    @patch('app.services.vector_store.mongodb_backup.get_mongo_db')
    def test_mongodb_backup_sync(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        
        backup = MongoDBBackup()
        
        chunks = [
            {"text": "hello", "vector": [0.1]*1024, "file_id": "f1", "source_language": "zh", "chunk_index": 0},
        ]
        backup.sync_to_mongodb(chunks)
        mock_collection.bulk_write.assert_called_once()

if __name__ == '__main__':
    unittest.main()
