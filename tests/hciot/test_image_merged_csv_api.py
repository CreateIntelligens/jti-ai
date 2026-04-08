import unittest
from pathlib import Path
import os
import shutil
from unittest import mock
from fastapi.testclient import TestClient
from tests.support.app_test_support import get_test_app
from app.routers.hciot.images import _IMAGES_DIR

app = get_test_app()

class TestImageAndMergedCsvApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_dir = _IMAGES_DIR
        os.makedirs(cls.test_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir)

    def tearDown(self):
        for f in self.test_dir.iterdir():
            if f.is_file():
                f.unlink()

    def test_list_images_empty(self):
        res = self.client.get("/api/hciot-admin/images/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"images": []})

    def test_upload_image_without_id(self):
        files = {"file": ("test.png", b"fakeimage", "image/png")}
        res = self.client.post("/api/hciot-admin/images/upload", files=files)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["filename"], "test.png")
        self.assertEqual(data["image_id"], "test")

    def test_upload_image_with_id(self):
        files = {"file": ("test.png", b"fakeimage", "image/png")}
        data = {"image_id": "my_img"}
        res = self.client.post("/api/hciot-admin/images/upload", files=files, data=data)
        self.assertEqual(res.status_code, 201)
        res_data = res.json()
        self.assertEqual(res_data["filename"], "my_img.png")
        self.assertEqual(res_data["image_id"], "my_img")

    def test_delete_image(self):
        (self.test_dir / "to_del.jpg").write_bytes(b"data")
        res = self.client.delete("/api/hciot-admin/images/to_del.jpg")
        self.assertEqual(res.status_code, 200)
        self.assertFalse((self.test_dir / "to_del.jpg").exists())

    def test_delete_missing_image(self):
        res = self.client.delete("/api/hciot-admin/images/missing.jpg")
        self.assertEqual(res.status_code, 404)
        
    @mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store")
    def test_merged_csv_api_empty(self, mock_store_factory):
        mock_store = mock.Mock()
        mock_store.get_topic_csv_files.return_value = []
        mock_store_factory.return_value = mock_store
        
        res = self.client.get("/api/hciot-admin/knowledge/topic-csv-merged?topic_id=test")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"rows": [], "source_files": []})

    @mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store")
    def test_merged_csv_api_with_data(self, mock_store_factory):
        mock_store = mock.Mock()
        mock_store.get_topic_csv_files.return_value = [
            {
                "filename": "a.csv",
                "data": b"index,q,a,img\n1,Q1,A1,\n"
            },
            {
                "filename": "b.csv",
                "data": b"index,q,a,img\n2,Q2,A2,img2\n"
            }
        ]
        mock_store_factory.return_value = mock_store
        
        res = self.client.get("/api/hciot-admin/knowledge/topic-csv-merged?topic_id=test")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["source_files"], ["a.csv", "b.csv"])
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["rows"][0]["q"], "Q1")
        self.assertEqual(data["rows"][1]["img"], "img2")
