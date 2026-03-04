"""Tests for KnowledgeStore namespace isolation."""

import sys
import unittest
from unittest.mock import MagicMock

mock_db = MagicMock()
mock_mongo_client_module = MagicMock()
mock_mongo_client_module.get_mongo_db.return_value = mock_db
sys.modules.setdefault("app.services.mongo_client", mock_mongo_client_module)

from app.services.knowledge_store import KnowledgeStore


class FakeCursor(list):
    def sort(self, *_args, **_kwargs):
        return list(self)


class TestKnowledgeStoreNamespace(unittest.TestCase):
    def setUp(self):
        self.store = KnowledgeStore()
        self.col = self.store.collection
        self.col.reset_mock(return_value=True, side_effect=True)

    def test_query_includes_namespace_default(self):
        q = self.store._query("zh", "test.txt")
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

    def test_list_files_default_namespace(self):
        self.col.find.return_value.sort.return_value = []
        self.store.list_files("zh")
        call_args = self.col.find.call_args_list[0][0][0]
        assert call_args["namespace"] == "jti"

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

    def test_get_file_falls_back_to_legacy_jti(self):
        self.col.find_one.side_effect = [
            None,
            {"filename": "legacy.txt", "display_name": "legacy.txt", "data": b"legacy"},
        ]
        doc = self.store.get_file("zh", "legacy.txt")
        assert doc is not None
        assert doc["data"] == b"legacy"
        assert self.col.find_one.call_args_list[1][0][0] == {
            "namespace": {"$exists": False},
            "language": "zh",
            "filename": "legacy.txt",
        }

    def test_hciot_get_file_does_not_fall_back_to_legacy(self):
        self.col.find_one.return_value = None
        result = self.store.get_file("zh", "test.txt", namespace="hciot")
        assert result is None
        assert self.col.find_one.call_count == 1

    def test_list_files_merges_legacy_jti_docs(self):
        self.col.find.side_effect = [
            FakeCursor([{"filename": "new.txt", "display_name": "new.txt", "size": 3, "editable": True}]),
            FakeCursor(
                [
                    {"filename": "legacy.txt", "display_name": "legacy.txt", "size": 5, "editable": True},
                    {"filename": "new.txt", "display_name": "new.txt", "size": 99, "editable": True},
                ]
            ),
        ]
        files = self.store.list_files("zh")
        assert [f["name"] for f in files] == ["legacy.txt", "new.txt"]

    def test_insert_file_checks_legacy_duplicate_for_jti(self):
        self.col.find_one.side_effect = [
            None,
            {"_id": "legacy-doc"},
            None,
            None,
        ]
        self.col.insert_one.return_value = MagicMock()
        result = self.store.insert_file(
            language="zh",
            filename="test.txt",
            data=b"hello",
        )
        assert result["filename"] == "test_1.txt"

    def test_update_file_content_passes_namespace(self):
        self.col.find_one_and_update.return_value = None
        self.store.update_file_content("zh", "test.txt", b"new", namespace="general")
        call_args = self.col.find_one_and_update.call_args[0][0]
        assert call_args["namespace"] == "general"


if __name__ == "__main__":
    unittest.main()
