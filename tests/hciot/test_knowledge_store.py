import sys
import unittest
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


fake_collection = FakeCollection()
fake_db = {"knowledge_files": fake_collection}

# Override the mock db with our fake collection
install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

from app.services.hciot.knowledge_store import HciotKnowledgeStore


class TestHciotKnowledgeStore(unittest.TestCase):
    def setUp(self):
        fake_collection.docs.clear()
        self.store = HciotKnowledgeStore()

    def test_insert_and_list_files_include_topic_metadata(self):
        created = self.store.insert_file(
            language="zh",
            filename="guide.csv",
            data=b"q\nhello",
            display_name="Guide",
            content_type="text/csv",
            editable=True,
            topic_id="general-medicine/diet",
            category_labels={"zh": "一般醫學", "en": "General Medicine"},
            topic_labels={"zh": "飲食", "en": "Diet"},
        )

        self.assertEqual(created["topic_id"], "general-medicine/diet")
        self.assertEqual(created["category_label_zh"], "一般醫學")
        self.assertEqual(created["topic_label_en"], "Diet")

        listed = self.store.list_files("zh")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["topic_id"], "general-medicine/diet")

    def test_update_file_metadata_persists_topic_assignment(self):
        self.store.insert_file(
            language="zh",
            filename="guide.txt",
            data=b"hello",
            display_name="Guide",
            content_type="text/plain",
            editable=True,
        )

        updated = self.store.update_file_metadata(
            language="zh",
            filename="guide.txt",
            metadata={
                "topic_id": "general-medicine/diet",
                "category_label_zh": "一般醫學",
                "category_label_en": "General Medicine",
                "topic_label_zh": "飲食",
                "topic_label_en": "Diet",
            },
        )

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["topic_id"], "general-medicine/diet")
        self.assertEqual(updated["topic_label_zh"], "飲食")

        fetched = self.store.get_file("zh", "guide.txt")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["topic_id"], "general-medicine/diet")


if __name__ == "__main__":
    unittest.main()
