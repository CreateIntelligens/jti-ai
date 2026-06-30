import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
LEGACY_TABLE_NAME_ENV = "LANCEDB_" + "TABLE_NAME"

sys.path.append(REPO_ROOT)
mock_lancedb = MagicMock()
sys.modules["lancedb"] = mock_lancedb

lancedb_module = importlib.import_module("app.services.vector_store.lancedb")
LanceDBStore = lancedb_module.LanceDBStore


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        lancedb_module._lancedb_store = None
        self.addCleanup(setattr, lancedb_module, "_lancedb_store", None)
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
        chunks = [
            {
                "text": "hello",
                "vector": [0.1] * 1024,
                "file_id": "f1",
                "source_language": "zh",
                "chunk_index": 0,
            },
        ]
        store.insert_chunks(chunks)
        mock_table.add.assert_called_once()

        mock_query = MagicMock()
        mock_table.search.return_value = mock_query
        mock_query.distance_type.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.to_list.return_value = [{"text": "hello"}]

        results = store.search(np.array([0.1] * 1024), language="zh", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "hello")

    def test_get_all_fingerprints_returns_mapping(self):
        """Batch fingerprint fetch returns {file_id: fingerprint} for a source/lang."""
        mock_db = MagicMock()
        mock_lancedb.connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = ["knowledge"]
        mock_table = MagicMock()
        mock_db.open_table.return_value = mock_table

        store = LanceDBStore(uri="memory://", table_name="knowledge")

        mock_query = MagicMock()
        mock_table.search.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.limit.return_value = mock_query
        # Multiple chunks per file share the same file_fingerprint; result is deduped per file_id.
        mock_query.to_list.return_value = [
            {"file_id": "f1", "file_fingerprint": "aaa"},
            {"file_id": "f1", "file_fingerprint": "aaa"},
            {"file_id": "f2", "file_fingerprint": "bbb"},
        ]

        fps = store.get_all_fingerprints("knowledge_general__store__", "zh")
        self.assertEqual(fps, {"f1": "aaa", "f2": "bbb"})

    def test_get_all_fingerprints_empty_when_no_table(self):
        """No table → empty mapping, never raises."""
        mock_db = MagicMock()
        mock_lancedb.connect.return_value = mock_db
        mock_db.list_tables.return_value.tables = []  # table absent
        store = LanceDBStore(uri="memory://", table_name="knowledge")
        self.assertEqual(store.get_all_fingerprints("knowledge_jti", "en"), {})

    def test_get_lancedb_store_ignores_legacy_table_name_env(self):
        with patch.dict(
            os.environ,
            {"LANCEDB_PATH": "memory://", LEGACY_TABLE_NAME_ENV: "legacy_name"},
        ):
            store = lancedb_module.get_lancedb_store()

        self.assertEqual(store.table_name, "knowledge")


if __name__ == "__main__":
    unittest.main()
