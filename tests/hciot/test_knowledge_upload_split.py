from unittest import mock

from fastapi.testclient import TestClient

from app.auth import verify_admin, verify_auth
from tests.support.app_test_support import get_test_app


app = get_test_app()
app.dependency_overrides[verify_admin] = lambda: {"role": "admin"}
app.dependency_overrides[verify_auth] = lambda: {"role": "admin"}


class FakeKnowledgeStore:
    def __init__(self):
        self.files: list[dict] = []

    def insert_file(
        self,
        language: str,
        filename: str,
        data: bytes,
        display_name: str | None = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
        topic_id: str | None = None,
        category_label: str | None = None,
        topic_label: str | None = None,
    ) -> dict:
        record = {
            "language": language,
            "filename": filename,
            "data": data,
            "display_name": display_name or filename,
            "content_type": content_type,
            "editable": editable,
            "topic_id": topic_id,
            "category_label": category_label,
            "topic_label": topic_label,
        }
        self.files.append(record)
        return {
            "name": filename,
            "display_name": record["display_name"],
            "size": len(data),
            "topic_id": topic_id,
            "category_label": record["category_label"],
            "topic_label": record["topic_label"],
        }

    def get_file(self, language: str, filename: str) -> dict | None:
        for item in self.files:
            if item["language"] == language and item["filename"] == filename:
                return {
                    **item,
                    "name": item["filename"],
                    "size": len(item["data"]),
                }
        return None

    def list_files(self, language: str) -> list[dict]:
        return [
            {
                "name": item["filename"],
                "display_name": item["display_name"],
                "size": len(item["data"]),
                "topic_id": item["topic_id"],
                "category_label": item["category_label"],
                "topic_label": item["topic_label"],
            }
            for item in self.files
            if item["language"] == language
        ]

    def update_file_content(self, language: str, filename: str, new_data: bytes) -> dict | None:
        for item in self.files:
            if item["language"] == language and item["filename"] == filename:
                item["data"] = new_data
                return {
                    "name": item["filename"],
                    "display_name": item["display_name"],
                    "size": len(new_data),
                    "topic_id": item["topic_id"],
                    "category_label": item["category_label"],
                    "topic_label": item["topic_label"],
                }
        return None

    def delete_file(self, language: str, filename: str) -> bool:
        original_len = len(self.files)
        self.files = [
            item for item in self.files
            if not (item["language"] == language and item["filename"] == filename)
        ]
        return len(self.files) != original_len

    def get_topic_csv_files(self, language: str, topic_id: str) -> list[dict]:
        return [
            {"filename": item["filename"], "data": item["data"]}
            for item in self.files
            if item["language"] == language and item["topic_id"] == topic_id and item["filename"].lower().endswith(".csv")
        ]


def _post_upload(client: TestClient, fake_store: FakeKnowledgeStore, fake_topic_store: mock.Mock, csv_bytes: bytes):
    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        return client.post(
            "/api/hciot-admin/knowledge/upload/?language=zh",
            files={"file": ("prp.csv", csv_bytes, "text/csv")},
            data={
                "category_id": "ortho",
                "topic_id": "prp",
                "category_label": "骨科",
                "topic_label": "PRP",
            },
        )


def _make_upload_context():
    return TestClient(app), FakeKnowledgeStore(), mock.Mock()


def test_list_knowledge_files_returns_empty_language_partition_without_chinese_fallback():
    client, fake_store, _ = _make_upload_context()
    fake_store.insert_file(
        language="zh",
        filename="zh.csv",
        data=b"index,q,a,img\n1,zh q,zh a,\n",
        display_name="zh.csv",
        content_type="text/csv",
        editable=True,
        topic_id="faq/hospital",
        category_label="常見問題",
        topic_label="醫院資訊",
    )

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store):
        response = client.get("/api/hciot-admin/knowledge/files/?language=en")

    assert response.status_code == 200
    assert response.json() == {"files": [], "language": "en"}


def test_upload_knowledge_file_splits_mixed_qa_csv_and_syncs_all_questions():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = (
        b"index,q,a,img\n"
        b"PRP_001,\xe7\x84\xa1\xe5\x9c\x96\xe5\x95\x8f\xe9\xa1\x8c,\xe7\x84\xa1\xe5\x9c\x96\xe7\xad\x94\xe6\xa1\x88,\n"
        b"PRP_002,\xe6\x9c\x89\xe5\x9c\x96\xe5\x95\x8f\xe9\xa1\x8c,\xe6\x9c\x89\xe5\x9c\x96\xe7\xad\x94\xe6\xa1\x88,IMG_T02_001\n"
    )

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 200
    assert response.json()["uploaded_count"] == 2
    assert [item["filename"] for item in fake_store.files] == [
        "prp.csv",
        "prp_IMG_T02_001.csv",
    ]

    fake_topic_store.upsert_topic.assert_called_once()
    _, topic_payload = fake_topic_store.upsert_topic.call_args.args
    assert topic_payload["questions"] == {
        "zh": ["無圖問題", "有圖問題"],
        "en": [],
    }


def test_upload_knowledge_file_with_only_image_rows_still_syncs_questions():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = (
        b"index,q,a,img\n"
        b"PRP_001,\xe7\xac\xac\xe4\xb8\x80\xe9\xa1\x8c,\xe7\xac\xac\xe4\xb8\x80\xe7\xad\x94,IMG_T02_001\n"
        b"PRP_002,\xe7\xac\xac\xe4\xba\x8c\xe9\xa1\x8c,\xe7\xac\xac\xe4\xba\x8c\xe7\xad\x94,IMG_T02_002\n"
    )

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 200
    assert response.json()["uploaded_count"] == 2
    assert [item["filename"] for item in fake_store.files] == [
        "prp_IMG_T02_001.csv",
        "prp_IMG_T02_002.csv",
    ]

    fake_topic_store.upsert_topic.assert_called_once()
    _, topic_payload = fake_topic_store.upsert_topic.call_args.args
    assert topic_payload["questions"] == {
        "zh": ["第一題", "第二題"],
        "en": [],
    }


def test_upload_knowledge_file_prefixes_non_img_image_rows_with_img_marker():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = (
        b"index,q,a,img\n"
        b'1,\xe7\xac\xac\xe4\xb8\x80\xe9\xa1\x8c,\xe7\xac\xac\xe4\xb8\x80\xe7\xad\x94,\xe7\x9f\xb3\xe9\xa0\xad\n'
        b"2,\xe7\xac\xac\xe4\xba\x8c\xe9\xa1\x8c,\xe7\xac\xac\xe4\xba\x8c\xe7\xad\x94,1763374588393\n"
    )

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 200
    assert [item["filename"] for item in fake_store.files] == [
        "prp_IMG_row_001.csv",
        "prp_IMG_1763374588393.csv",
    ]


def test_upload_knowledge_file_preserves_image_extension_in_split_filename():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = (
        b"index,q,a,img\n"
        b"1,\xe7\xac\xac\xe4\xb8\x80\xe9\xa1\x8c,\xe7\xac\xac\xe4\xb8\x80\xe7\xad\x94,images/IMG_T02_001.jpeg\n"
    )

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 200
    assert [item["filename"] for item in fake_store.files] == [
        "prp_IMG_T02_001.jpeg.csv",
    ]


def test_upload_rejects_qa_like_csv_without_question_column():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = "項目,內容,圖片 (img),網址 (URL)\n股四頭肌是什麼？,大腿前側肌肉,IMG_1,\n".encode()

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 400
    assert "q" in response.json()["detail"]
    assert fake_store.files == []
    fake_topic_store.upsert_topic.assert_not_called()


def test_upload_rejects_qa_csv_without_answer_column():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = "q,img\n股四頭肌是什麼？,IMG_1\n".encode()

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 400
    assert "a" in response.json()["detail"]
    assert fake_store.files == []
    fake_topic_store.upsert_topic.assert_not_called()


def test_upload_accepts_qa_csv_without_index_and_backfills_it():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None

    csv_bytes = "q,a,img\n第一題,第一答,\n第二題,第二答,\n".encode()

    response = _post_upload(client, fake_store, fake_topic_store, csv_bytes)

    assert response.status_code == 200
    saved = fake_store.get_file("zh", "prp.csv")
    assert saved is not None
    assert saved["data"].decode("utf-8-sig") == "index,q,a,img\n1,第一題,第一答,\n2,第二題,第二答,\n"


def test_update_file_content_splits_legacy_single_csv_with_image_rows():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None
    fake_store.insert_file(
        language="zh",
        filename="legacy.csv",
        data=b"index,q,a,img\n1,\xe8\x88\x8a\xe9\xa1\x8c,\xe8\x88\x8a\xe7\xad\x94,\n",
        display_name="legacy.csv",
        content_type="text/csv",
        editable=True,
        topic_id="ortho/legacy",
        category_label="骨科",
        topic_label="舊題庫",
    )

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        response = client.put(
            "/api/hciot-admin/knowledge/files/legacy.csv/content?language=zh",
            json={
                "content": (
                    "index,q,a,img\n"
                    "1,第一題,第一答,IMG_T02_001\n"
                    "2,第二題,第二答,IMG_T02_002\n"
                )
            },
        )

    assert response.status_code == 200
    assert sorted(item["filename"] for item in fake_store.files) == [
        "legacy_IMG_T02_001.csv",
        "legacy_IMG_T02_002.csv",
    ]
    fake_topic_store.upsert_topic.assert_called_once()
    _, topic_payload = fake_topic_store.upsert_topic.call_args.args
    assert topic_payload["questions"] == {
        "zh": ["第一題", "第二題"],
        "en": [],
    }


def test_update_file_content_keeps_canonical_name_for_existing_img_csv():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None
    fake_store.insert_file(
        language="zh",
        filename="legacy_IMG_T02_001.csv",
        data=b"index,q,a,img\n1,\xe7\xac\xac\xe4\xb8\x80\xe9\xa1\x8c,\xe7\xac\xac\xe4\xb8\x80\xe7\xad\x94,IMG_T02_001\n",
        display_name="legacy_IMG_T02_001.csv",
        content_type="text/csv",
        editable=True,
        topic_id="ortho/legacy",
        category_label="骨科",
        topic_label="舊題庫",
    )

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        response = client.put(
            "/api/hciot-admin/knowledge/files/legacy_IMG_T02_001.csv/content?language=zh",
            json={"content": "index,q,a,img\n1,第一題,第一答,IMG_T02_001\n"},
        )

    assert response.status_code == 200
    assert [item["filename"] for item in fake_store.files] == ["legacy_IMG_T02_001.csv"]


def test_update_file_content_drops_blank_rows_from_csv_save():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None
    fake_store.insert_file(
        language="zh",
        filename="legacy.csv",
        data=b"index,q,a,img\n1,\xe8\x88\x8a\xe9\xa1\x8c,\xe8\x88\x8a\xe7\xad\x94,\n",
        display_name="legacy.csv",
        content_type="text/csv",
        editable=True,
        topic_id="ortho/legacy",
        category_label="骨科",
        topic_label="舊題庫",
    )

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        response = client.put(
            "/api/hciot-admin/knowledge/files/legacy.csv/content?language=zh",
            json={"content": "index,q,a,img\n1,第一題,第一答,\n2,,,\n"},
        )

    assert response.status_code == 200
    saved = fake_store.get_file("zh", "legacy.csv")
    assert saved is not None
    assert saved["data"].decode("utf-8-sig") == "index,q,a,img\n1,第一題,第一答,\n"


def test_update_file_content_rejects_qa_like_csv_without_question_column():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None
    fake_store.insert_file(
        language="zh",
        filename="legacy.csv",
        data=b"index,q,a,img\n1,\xe8\x88\x8a\xe9\xa1\x8c,\xe8\x88\x8a\xe7\xad\x94,\n",
        display_name="legacy.csv",
        content_type="text/csv",
        editable=True,
        topic_id="ortho/legacy",
        category_label="骨科",
        topic_label="舊題庫",
    )

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        response = client.put(
            "/api/hciot-admin/knowledge/files/legacy.csv/content?language=zh",
            json={"content": "項目,內容,圖片 (img),網址 (URL)\n股四頭肌是什麼？,大腿前側肌肉,IMG_1,\n"},
        )

    assert response.status_code == 400
    assert "q" in response.json()["detail"]
    saved = fake_store.get_file("zh", "legacy.csv")
    assert saved is not None
    assert saved["data"].decode("utf-8-sig") == "index,q,a,img\n1,舊題,舊答,\n"


def test_update_file_content_rejects_qa_csv_without_answer_column():
    client, fake_store, fake_topic_store = _make_upload_context()
    fake_topic_store.get_topic.return_value = None
    fake_store.insert_file(
        language="zh",
        filename="legacy.csv",
        data=b"index,q,a,img\n1,\xe8\x88\x8a\xe9\xa1\x8c,\xe8\x88\x8a\xe7\xad\x94,\n",
        display_name="legacy.csv",
        content_type="text/csv",
        editable=True,
        topic_id="ortho/legacy",
        category_label="骨科",
        topic_label="舊題庫",
    )

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        response = client.put(
            "/api/hciot-admin/knowledge/files/legacy.csv/content?language=zh",
            json={"content": "q,img\n股四頭肌是什麼？,IMG_1\n"},
        )

    assert response.status_code == 400
    assert "a" in response.json()["detail"]
    saved = fake_store.get_file("zh", "legacy.csv")
    assert saved is not None
    assert saved["data"].decode("utf-8-sig") == "index,q,a,img\n1,舊題,舊答,\n"
