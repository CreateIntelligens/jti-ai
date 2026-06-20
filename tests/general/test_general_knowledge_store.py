import sys
import unittest
import importlib

from tests.support.app_test_support import install_app_import_mocks
from tests.support.fake_mongo import FakeCollection


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
