import importlib
import sys
import unittest

from tests.support.app_test_support import install_app_import_mocks
from tests.support.fake_mongo import FakeCollection


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
