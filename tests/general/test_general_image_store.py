import importlib
import sys
import unittest

from tests.support.app_test_support import install_app_import_mocks


class FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FakeUpdateResult:
    def __init__(self, upserted_id):
        self.upserted_id = upserted_id


class FakeCursor(list):
    def sort(self, key, direction):
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
            self.docs.append({**set_on_insert, **set_data})
            return FakeUpdateResult(upserted_id="fake-upserted-id")
        return FakeUpdateResult(upserted_id=None)


fake_collection = FakeCollection()
fake_db = {"general_images": fake_collection}

install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

image_store_module = importlib.import_module("app.services.general.image_store")
image_store_module = importlib.reload(image_store_module)
GeneralImageStore = image_store_module.GeneralImageStore


class TestGeneralImageStore(unittest.TestCase):
    def setUp(self):
        fake_collection.docs.clear()
        self.store = GeneralImageStore()

    def test_images_isolated_by_store_name(self):
        self.store.upsert_image("store-a", "logo", b"\x89PNG", "image/png")

        self.assertTrue(self.store.image_exists("store-a", "logo"))
        self.assertFalse(self.store.image_exists("store-b", "logo"))

        ids = [i["image_id"] for i in self.store.list_images("store-a")]
        self.assertIn("logo", ids)
        self.assertEqual(self.store.list_images("store-b"), [])

    def test_get_returns_bytes_and_url_is_store_scoped(self):
        self.store.upsert_image("store-a", "logo", b"data", "image/png")

        got = self.store.get_image("store-a", "logo")
        self.assertEqual(got["data"], b"data")
        self.assertEqual(got["content_type"], "image/png")

        listed = self.store.list_images("store-a")[0]
        self.assertEqual(listed["url"], "/api/general/stores/store-a/images/logo")

    def test_delete_image(self):
        self.store.upsert_image("store-a", "logo", b"data")
        self.assertTrue(self.store.delete_image("store-a", "logo"))
        self.assertFalse(self.store.delete_image("store-a", "logo"))
        self.assertIsNone(self.store.get_image("store-a", "logo"))


if __name__ == "__main__":
    unittest.main()
