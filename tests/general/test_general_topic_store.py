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

    def find_one_and_update(self, query: dict, update: dict, return_document=None, upsert=False, projection: dict | None = None):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                updated = dict(doc)
                for key, value in update.get("$set", {}).items():
                    updated[key] = value
                self.docs[index] = updated
                return self._project(updated, projection)

        # Not found and upsert=True: create new doc
        if upsert:
            new_doc = dict(query)  # Start with query fields
            for key, value in update.get("$set", {}).items():
                new_doc[key] = value
            for key, value in update.get("$setOnInsert", {}).items():
                new_doc[key] = value
            self.docs.append(new_doc)
            return self._project(new_doc, projection)
        return None

    def delete_one(self, query: dict):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(index)
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)

    def delete_many(self, query: dict):
        deleted = 0
        for index in range(len(self.docs) - 1, -1, -1):
            if self._matches(self.docs[index], query):
                self.docs.pop(index)
                deleted += 1
        return FakeDeleteResult(deleted)

    def count_documents(self, query: dict, limit: int | None = None):
        count = 0
        for doc in self.docs:
            if self._matches(doc, query):
                count += 1
                if limit and count >= limit:
                    return count
        return count


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
