from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from app.auth import verify_admin, verify_auth
from app.routers.knowledge_utils import sync_gemini_db_background
from tests.support.app_test_support import get_test_app


app = get_test_app()
app.dependency_overrides[verify_admin] = lambda: {"role": "admin"}
app.dependency_overrides[verify_auth] = lambda: {"role": "admin"}


class FakeSyncStore:
    def __init__(self, files: list[dict] | None = None):
        self.files = list(files or [])
        self.insert_calls: list[dict] = []
        self.delete_calls: list[tuple[str, str]] = []

    def list_files(self, language: str) -> list[dict]:
        return list(self.files)

    def delete_file(self, language: str, filename: str) -> bool:
        self.delete_calls.append((language, filename))
        return True

    def insert_file(self, language: str, filename: str, data: bytes, **kwargs) -> dict:
        call = {
            "language": language,
            "filename": filename,
            "data": data,
            **kwargs,
        }
        self.insert_calls.append(call)
        return {"name": filename}


def test_sync_gemini_db_background_skips_gemini_only_registration_when_disabled():
    store = FakeSyncStore()
    gemini_docs = [SimpleNamespace(display_name="orphan.csv")]

    with (
        mock.patch("app.routers.knowledge_utils._get_or_create_manager", return_value=mock.Mock()),
        mock.patch("app.routers.knowledge_utils._list_files_with_retry", return_value=gemini_docs),
    ):
        sync_gemini_db_background(
            "fileSearchStores/test",
            store,
            "zh",
            "HCIoT sync",
            register_gemini_only=False,
        )

    assert store.insert_calls == []


def test_sync_gemini_db_background_still_registers_gemini_only_by_default():
    store = FakeSyncStore()
    gemini_docs = [SimpleNamespace(display_name="orphan.csv")]

    with (
        mock.patch("app.routers.knowledge_utils._get_or_create_manager", return_value=mock.Mock()),
        mock.patch("app.routers.knowledge_utils._list_files_with_retry", return_value=gemini_docs),
    ):
        sync_gemini_db_background("fileSearchStores/test", store, "zh", "JTI sync")

    assert store.insert_calls == [{
        "language": "zh",
        "filename": "orphan.csv",
        "data": b"",
        "editable": False,
    }]


def test_hciot_list_knowledge_files_disables_gemini_only_placeholder_registration():
    client = TestClient(app)
    fake_store = mock.Mock()
    fake_store.list_files.return_value = []

    with (
        mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_store),
        mock.patch("app.routers.hciot.knowledge.start_background_sync") as start_background_sync,
    ):
        response = client.get("/api/hciot-admin/knowledge/files/?language=zh")

    assert response.status_code == 200
    assert response.json()["files"] == []
    start_background_sync.assert_called_once()
    assert start_background_sync.call_args.kwargs["register_gemini_only"] is False
