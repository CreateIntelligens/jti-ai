import sys
import unittest
import importlib

from tests.support.app_test_support import install_app_import_mocks
from tests.support.fake_mongo import FakeCollection


fake_topics_collection = FakeCollection()
fake_categories_collection = FakeCollection()
fake_db = {
    "general_topics": fake_topics_collection,
    "general_categories": fake_categories_collection,
}

# Override the mock db with our fake collections
install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

# Reload base FIRST — it owns the `from app.services.mongo_client import get_mongo_db`
# reference, and without this reload it keeps a stale binding from earlier tests'
# mongo_client mock. Then reload the general subclass so its base lookup points
# at the freshly-bound module.
base_module = importlib.import_module("app.services._shared.qa_kb.topic_store_base")
importlib.reload(base_module)
topic_store_module = importlib.import_module("app.services.general.topic_store")
topic_store_module = importlib.reload(topic_store_module)
get_general_topic_store = topic_store_module.get_general_topic_store


class TestGeneralTopicStore(unittest.TestCase):
    def setUp(self):
        fake_topics_collection.docs.clear()
        fake_categories_collection.docs.clear()
        # Patch get_mongo_db on the base module directly (sibling test modules
        # rebind its imported reference); restore on cleanup to avoid leaking
        # our fake db into other test modules.
        import app.services._shared.qa_kb.topic_store_base as tb_base
        orig = tb_base.get_mongo_db
        tb_base.get_mongo_db = lambda *_a, **_k: fake_db
        self.addCleanup(setattr, tb_base, "get_mongo_db", orig)

    def test_topics_isolated_by_store_name(self):
        """Verify per-store isolation: store_name passed in language parameter slot."""
        a = get_general_topic_store("store-a")
        b = get_general_topic_store("store-b")

        a.upsert_topic("greetings", {"labels": "Greetings", "questions": ["hi"]})

        a_ids = [t["topic_id"] for t in a.list_topics()]
        b_ids = [t["topic_id"] for t in b.list_topics()]

        self.assertIn("greetings", a_ids)
        self.assertNotIn("greetings", b_ids)

        # cleanup
        a.delete_topic("greetings")


if __name__ == "__main__":
    unittest.main()
