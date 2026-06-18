import sys
import unittest
import importlib
from unittest.mock import MagicMock

from tests.support.app_test_support import install_app_import_mocks


class FakeInsertResult:
    inserted_id = "fake-id"


class FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FakeCursor(list):
    def sort(self, key: str, direction: int):
        reverse = direction < 0
        return FakeCursor(sorted(self, key=lambda item: item.get(key, ""), reverse=reverse))


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        return all(doc.get(key) == value for key, value in query.items())

    @staticmethod
    def _project(doc: dict, projection: dict | None) -> dict:
        if not projection:
            return dict(doc)

        include_keys = [key for key, value in projection.items() if value]
        if include_keys:
            return {key: doc.get(key) for key in include_keys if key in doc}

        result = dict(doc)
        for key, value in projection.items():
            if value == 0:
                result.pop(key, None)
        return result

    def find_one(self, query: dict, projection: dict | None = None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._project(doc, projection)
        return None

    def insert_one(self, doc: dict):
        self.docs.append(dict(doc))
        return FakeInsertResult()

    def find(self, query: dict, projection: dict | None = None):
        return FakeCursor(
            [self._project(doc, projection) for doc in self.docs if self._matches(doc, query)]
        )

    def find_one_and_update(self, query: dict, update: dict, return_document=None):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                updated = dict(doc)
                for key, value in update.get("$set", {}).items():
                    updated[key] = value
                self.docs[index] = updated
                return dict(updated)
        return None

    def delete_one(self, query: dict):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(index)
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)

    def count_documents(self, query: dict, limit: int | None = None):
        count = 0
        for doc in self.docs:
            if self._matches(doc, query):
                count += 1
                if limit and count >= limit:
                    return count
        return count


fake_collection = FakeCollection()
fake_db = {"general_knowledge_files": fake_collection}

# Override the mock db with our fake collection
install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

# Reload base FIRST — it owns the `from app.services.mongo_client import get_mongo_db`
# reference, and without this reload it keeps a stale binding from earlier tests'
# mongo_client mock, causing find_one() to return a truthy MagicMock and turning
# `_resolve_filename`'s `while` loop into an unbounded string allocation. Then
# reload the general subclass so its base lookup points at the freshly-bound module.
base_module = importlib.import_module("app.services._shared.qa_kb.knowledge_store_base")
importlib.reload(base_module)
knowledge_store_module = importlib.import_module("app.services.general.knowledge_store")
knowledge_store_module = importlib.reload(knowledge_store_module)
GeneralKnowledgeStore = knowledge_store_module.GeneralKnowledgeStore


class TestGeneralKnowledgeStore(unittest.TestCase):
    def setUp(self):
        fake_collection.docs.clear()
        # Patch get_mongo_db on the base module directly: sibling test modules
        # reload it and rebind its imported reference to a fresh mock, so just
        # setting sys.modules' mock is not enough. Restore on cleanup so this
        # test does not leak its fake db into sibling test modules.
        import app.services._shared.qa_kb.knowledge_store_base as kb_base
        orig = kb_base.get_mongo_db
        kb_base.get_mongo_db = lambda *_a, **_k: fake_db
        self.addCleanup(setattr, kb_base, "get_mongo_db", orig)
        self.store = GeneralKnowledgeStore()

    def test_files_isolated_by_store_name(self):
        """Verify per-store isolation: store_name passed in language parameter slot."""
        self.store.insert_file("store-a", "faq.csv", b"q,a\nhi,hello\n", content_type="text/csv")
        self.store.insert_file("store-b", "faq.csv", b"q,a\nbye,goodbye\n", content_type="text/csv")

        a_files = [f["filename"] for f in self.store.list_files("store-a")]
        b_files = [f["filename"] for f in self.store.list_files("store-b")]

        self.assertIn("faq.csv", a_files)
        self.assertIn("faq.csv", b_files)

        a_doc = self.store.get_file("store-a", "faq.csv")
        self.assertIsNotNone(a_doc)
        assert a_doc is not None
        self.assertIn(b"hi,hello", a_doc["data"])

        b_doc = self.store.get_file("store-b", "faq.csv")
        self.assertIsNotNone(b_doc)
        assert b_doc is not None
        self.assertIn(b"bye,goodbye", b_doc["data"])

        # Cleanup
        self.store.delete_file("store-a", "faq.csv")
        self.store.delete_file("store-b", "faq.csv")

        # Verify isolation after cleanup
        a_files_after = [f["filename"] for f in self.store.list_files("store-a")]
        b_files_after = [f["filename"] for f in self.store.list_files("store-b")]
        self.assertNotIn("faq.csv", a_files_after)
        self.assertNotIn("faq.csv", b_files_after)


if __name__ == "__main__":
    unittest.main()
