import sys
import unittest
from datetime import datetime

from tests.support.app_test_support import install_app_import_mocks


class FakeInsertResult:
    inserted_id = "fake-id"


class FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FakeUpdateResult:
    def __init__(self, upserted_id):
        self.upserted_id = upserted_id


class FakeCursor(list):
    def sort(self, key: str, direction: int):
        reverse = direction < 0
        return FakeCursor(sorted(self, key=lambda item: item.get(key, ""), reverse=reverse))


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def create_index(self, *args, **kwargs):
        pass

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
        if any(d.get("image_id") == doc.get("image_id") for d in self.docs):
            raise Exception("Duplicate key")
        self.docs.append(dict(doc))
        return FakeInsertResult()

    def find(self, query: dict, projection: dict | None = None):
        return FakeCursor(
            [self._project(doc, projection) for doc in self.docs if self._matches(doc, query)]
        )

    def count_documents(self, query: dict, limit: int = 0):
        count = sum(1 for doc in self.docs if self._matches(doc, query))
        return min(count, limit) if limit else count

    def delete_one(self, query: dict):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(index)
                return FakeDeleteResult(1)
        return FakeDeleteResult(0)

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        set_data = update.get("$set", {})
        set_on_insert = update.get("$setOnInsert", {})
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(set_data)
                return FakeUpdateResult(upserted_id=None)
        if upsert:
            new_doc = {**set_on_insert, **set_data}
            self.docs.append(new_doc)
            return FakeUpdateResult(upserted_id="fake-upserted-id")
        return FakeUpdateResult(upserted_id=None)


fake_collection = FakeCollection()
fake_db = {"hciot_images": fake_collection}

# Override the mock db with our fake collection
install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

from app.services.hciot.image_store import HciotImageStore


class TestHciotImageStore(unittest.TestCase):
    def setUp(self):
        fake_collection.docs.clear()
        self.store = HciotImageStore()

    def test_upsert_and_get_image(self):
        data = b"fake-image-data"
        result = self.store.upsert_image("test-img", data, "image/png")
        self.assertTrue(result["success"])
        self.assertFalse(result["replaced"])

        image = self.store.get_image("test-img")
        self.assertIsNotNone(image)
        self.assertEqual(image["image_id"], "test-img")
        self.assertEqual(image["data"], data)
        self.assertEqual(image["content_type"], "image/png")
        self.assertIsInstance(image["created_at"], datetime)

    def test_upsert_replaces_existing(self):
        self.store.upsert_image("dup", b"data1")
        result = self.store.upsert_image("dup", b"data2")
        self.assertTrue(result["success"])
        self.assertTrue(result["replaced"])
        self.assertEqual(self.store.get_image("dup")["data"], b"data2")

    def test_list_images(self):
        self.store.upsert_image("img1", b"d1")
        self.store.upsert_image("img2", b"d2")

        images = self.store.list_images()
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]["image_id"], "img1")
        self.assertEqual(images[1]["image_id"], "img2")
        self.assertEqual(images[0]["url"], "/api/hciot/images/img1")
        self.assertIn("size_bytes", images[0])
        self.assertNotIn("data", images[0])

    def test_delete_image(self):
        self.store.upsert_image("to-delete", b"data")
        self.assertTrue(self.store.delete_image("to-delete"))
        self.assertIsNone(self.store.get_image("to-delete"))
        self.assertFalse(self.store.delete_image("nonexistent"))

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get_image("nothing"))


if __name__ == "__main__":
    unittest.main()
