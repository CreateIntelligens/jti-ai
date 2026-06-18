import unittest
from app.services.jti.quiz_bank_store import get_quiz_bank_store
from app.services.jti.quiz_results_store import get_quiz_results_store


class TestQuizStoreIsolation(unittest.TestCase):
    def setUp(self):
        import sys
        import importlib
        from unittest.mock import MagicMock

        if "app.services.mongo_client" in sys.modules:
            # Check if get_mongo_db is mocked
            mc = sys.modules["app.services.mongo_client"]
            if hasattr(mc, "get_mongo_db") and isinstance(mc.get_mongo_db, MagicMock):
                for mod in [
                    "app.services.mongo_client",
                    "app.services.jti.quiz_bank_store",
                    "app.services.jti.quiz_results_store"
                ]:
                    if mod in sys.modules:
                        del sys.modules[mod]
                importlib.import_module("app.services.mongo_client")

        from app.services.jti.quiz_bank_store import get_quiz_bank_store
        from app.services.jti.quiz_results_store import get_quiz_results_store

        self.bank_store = get_quiz_bank_store()
        self.results_store = get_quiz_results_store()

        # Clean up test data
        self.bank_store.metadata.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})
        self.bank_store.questions.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})
        self.results_store.metadata.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})
        self.results_store.collection.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})

    def tearDown(self):
        # Clean up test data
        self.bank_store.metadata.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})
        self.bank_store.questions.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})
        self.results_store.metadata.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})
        self.results_store.collection.delete_many({"store_name": {"$in": ["test_store_1", "test_store_2"]}})

    def test_bank_store_isolation(self):
        # Create bank in store 1
        bank_1 = self.bank_store.create_bank("zh", "Bank 1", store_name="test_store_1", clone_default=False)
        # Create bank in store 2 with same details
        bank_2 = self.bank_store.create_bank("zh", "Bank 2", store_name="test_store_2", clone_default=False)

        # Check banks list for each store
        banks_1 = self.bank_store.list_banks("zh", store_name="test_store_1")
        banks_2 = self.bank_store.list_banks("zh", store_name="test_store_2")

        self.assertEqual(len(banks_1), 1)
        self.assertEqual(banks_1[0]["name"], "Bank 1")

        self.assertEqual(len(banks_2), 1)
        self.assertEqual(banks_2[0]["name"], "Bank 2")

    def test_results_store_isolation(self):
        # Create set in store 1
        set_1 = self.results_store.create_set("zh", "Set 1", store_name="test_store_1")
        set_2 = self.results_store.create_set("zh", "Set 2", store_name="test_store_2")

        sets_1 = self.results_store.list_sets("zh", store_name="test_store_1")
        sets_2 = self.results_store.list_sets("zh", store_name="test_store_2")

        self.assertEqual(len(sets_1), 1)
        self.assertEqual(sets_1[0]["name"], "Set 1")

        self.assertEqual(len(sets_2), 1)
        self.assertEqual(sets_2[0]["name"], "Set 2")
