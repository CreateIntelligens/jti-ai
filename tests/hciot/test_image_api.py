import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from tests.support.app_test_support import install_app_import_mocks

# Setup mocks before importing app
install_app_import_mocks()
mock_store = MagicMock()
sys.modules["app.services.hciot.image_store"] = MagicMock()
sys.modules["app.services.hciot.image_store"].get_hciot_image_store.return_value = mock_store

from app.auth import verify_admin
from app.routers.hciot.images import router, admin_router
from fastapi import FastAPI

app = FastAPI()
app.dependency_overrides[verify_admin] = lambda: {"role": "admin"}
app.include_router(router, prefix="/api/hciot")
app.include_router(admin_router, prefix="/api/hciot-admin/images")


class TestImageApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.store_patcher = patch("app.routers.hciot.images.get_hciot_image_store", return_value=mock_store)
        self.store_patcher.start()
        mock_store.reset_mock()
        mock_store.get_image.side_effect = None
        mock_store.get_image.return_value = None

    def tearDown(self):
        self.store_patcher.stop()

    def test_get_image_success(self):
        mock_store.get_image.return_value = {
            "image_id": "test-id",
            "data": b"fake-data",
            "content_type": "image/png"
        }
        res = self.client.get("/api/hciot/images/test-id")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"fake-data")
        self.assertEqual(res.headers["content-type"], "image/png")

    def test_get_image_not_found(self):
        mock_store.get_image.return_value = None
        res = self.client.get("/api/hciot/images/missing")
        self.assertEqual(res.status_code, 404)

    def test_get_image_falls_back_from_img_prefixed_id(self):
        mock_store.get_image.side_effect = [
            None,
            {
                "image_id": "1",
                "data": b"fake-data",
                "content_type": "image/png",
            },
        ]

        res = self.client.get("/api/hciot/images/IMG_1")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"fake-data")
        self.assertEqual(mock_store.get_image.call_args_list[0].args, ("IMG_1",))
        self.assertEqual(mock_store.get_image.call_args_list[1].args, ("1",))

    def test_list_images(self):
        mock_store.list_images.return_value = [
            {"image_id": "img1", "url": "/api/hciot/images/img1"},
            {"image_id": "img2", "url": "/api/hciot/images/img2"}
        ]
        res = self.client.get("/api/hciot-admin/images/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["images"]), 2)

    def test_upload_image_success(self):
        mock_store.image_exists.return_value = False
        mock_store.insert_image.return_value = True
        
        files = {"file": ("test.png", b"fakeimage", "image/png")}
        res = self.client.post("/api/hciot-admin/images/upload", files=files)
        
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["image_id"], "test")
        self.assertEqual(data["url"], "/api/hciot/images/test")
        
    def test_upload_image_conflict(self):
        mock_store.image_exists.return_value = True
        
        files = {"file": ("exists.png", b"data", "image/png")}
        res = self.client.post("/api/hciot-admin/images/upload", files=files)
        self.assertEqual(res.status_code, 409)

    def test_delete_image_success(self):
        mock_store.delete_image.return_value = True
        res = self.client.delete("/api/hciot-admin/images/to-delete")
        self.assertEqual(res.status_code, 200)
        mock_store.delete_image.assert_called_with("to-delete")

    def test_delete_image_with_extension_legacy(self):
        mock_store.delete_image.return_value = True
        res = self.client.delete("/api/hciot-admin/images/to-delete.jpg")
        self.assertEqual(res.status_code, 200)
        mock_store.delete_image.assert_called_with("to-delete")

if __name__ == "__main__":
    unittest.main()
