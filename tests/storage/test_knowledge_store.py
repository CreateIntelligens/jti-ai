"""Tests for KnowledgeStore namespace isolation."""

import unittest
from unittest.mock import MagicMock, patch

mock_db = MagicMock()

from app.services.knowledge_store import KnowledgeStore, NamespacedKnowledgeStore


class FakeCursor(list):
    def sort(self, *_args, **_kwargs):
        return list(self)


class TestKnowledgeStoreNamespace(unittest.TestCase):
    def setUp(self):
        patcher = patch("app.services.knowledge_store.get_mongo_db", return_value=mock_db)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = KnowledgeStore(db_name="jti_app")
        self.col = self.store.collection
        self.col.reset_mock(return_value=True, side_effect=True)

    def test_query_includes_namespace_default(self):
        q = self.store._query("zh", "test.txt", namespace="jti")
        assert q == {"namespace": "jti", "language": "zh", "filename": "test.txt"}

    def test_query_includes_namespace_custom(self):
        q = self.store._query("en", "test.txt", namespace="general")
        assert q == {"namespace": "general", "language": "en", "filename": "test.txt"}

    def test_query_without_filename(self):
        q = self.store._query("zh", namespace="hciot")
        assert q == {"namespace": "hciot", "language": "zh"}

    def test_list_files_passes_namespace(self):
        self.col.find.return_value.sort.return_value = []
        self.store.list_files("zh", namespace="general")
        call_args = self.col.find.call_args[0][0]
        assert call_args["namespace"] == "general"

    def test_query_requires_namespace(self):
        with self.assertRaises(TypeError):
            self.store._query("zh", "test.txt")

    def test_delete_file_passes_namespace(self):
        self.col.delete_one.return_value.deleted_count = 1
        self.store.delete_file("zh", "test.txt", namespace="general")
        call_args = self.col.delete_one.call_args[0][0]
        assert call_args["namespace"] == "general"

    def test_delete_by_namespace(self):
        self.col.delete_many.return_value.deleted_count = 3
        result = self.store.delete_by_namespace("general", language="store/123")
        call_args = self.col.delete_many.call_args[0][0]
        assert call_args == {"namespace": "general", "language": "store/123"}
        assert result == 3

    def test_delete_by_namespace_without_language(self):
        self.col.delete_many.return_value.deleted_count = 5
        result = self.store.delete_by_namespace("general")
        call_args = self.col.delete_many.call_args[0][0]
        assert call_args == {"namespace": "general"}
        assert result == 5

    def test_insert_file_includes_namespace(self):
        self.col.find_one.return_value = None  # no duplicate
        self.col.insert_one.return_value = MagicMock()
        self.store.insert_file(
            language="store/abc",
            filename="test.txt",
            data=b"hello",
            namespace="general",
        )
        doc = self.col.insert_one.call_args[0][0]
        assert doc["namespace"] == "general"
        assert doc["language"] == "store/abc"

    def test_save_file_query_includes_namespace(self):
        self.col.find_one_and_update.return_value = {
            "filename": "test.txt", "size": 5, "editable": True,
        }
        self.store.save_file(
            language="zh",
            filename="test.txt",
            data=b"hello",
            namespace="general",
        )
        call_args = self.col.find_one_and_update.call_args
        query_filter = call_args[0][0]
        assert query_filter["namespace"] == "general"
        update_doc = call_args[0][1]["$set"]
        assert update_doc["namespace"] == "general"

    def test_get_file_passes_namespace(self):
        self.col.find_one.return_value = None
        self.store.get_file("zh", "test.txt", namespace="general")
        call_args = self.col.find_one.call_args[0][0]
        assert call_args["namespace"] == "general"

    def test_update_file_content_passes_namespace(self):
        self.col.find_one_and_update.return_value = None
        self.store.update_file_content("zh", "test.txt", b"new", namespace="general")
        call_args = self.col.find_one_and_update.call_args[0][0]
        assert call_args["namespace"] == "general"

    def test_namespaced_store_binds_namespace_for_calls(self):
        namespaced = NamespacedKnowledgeStore(self.store, "jti")
        self.col.find.side_effect = [FakeCursor([]), FakeCursor([])]

        namespaced.list_files("zh")

        first_call_args = self.col.find.call_args_list[0][0][0]
        assert first_call_args["namespace"] == "jti"


if __name__ == "__main__":
    unittest.main()
