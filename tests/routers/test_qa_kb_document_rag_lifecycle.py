"""Topic-less files (documents) must keep their RAG vectors in step with Mongo.

Upload and startup backfill index every supported file, topic or not. Edit and
delete only touched RAG for topic files, so a deleted or edited document kept
answering with its old content until the next backend restart.
"""
import unittest
from unittest import mock
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers._shared.qa_kb_router import QaKbRouterConfig, build_qa_kb_router
from app.utils import get_other_language

DOC = {
    "filename": "guide.txt",
    "topic_id": None,
    "data": b"old content",
    "content_type": "text/plain",
    "editable": True,
}


def _build_client(knowledge_store: MagicMock) -> TestClient:
    config = QaKbRouterConfig(
        tag="Test KB",
        app="hciot",
        knowledge_store_factory=lambda: knowledge_store,
        topic_store_factory=lambda language: MagicMock(),
        rag_source_type="hciot",
        invalidate_cache=lambda language=None: None,
        other_language=get_other_language,
    )
    with mock.patch(
        "app.routers._shared.qa_kb_router.require_kb_access",
        return_value=lambda: {"role": "admin"},
    ):
        router = build_qa_kb_router(config, include_knowledge=True)
    app = FastAPI()
    app.include_router(router, prefix="/knowledge")
    return TestClient(app)


class TestDocumentRagLifecycle(unittest.TestCase):
    def setUp(self):
        self.store = MagicMock()
        self.store.get_file.side_effect = lambda language, name: DOC if name == DOC["filename"] else None
        self.store.delete_file.return_value = True
        self.store.update_file_content.return_value = True
        self.client = _build_client(self.store)

    def test_deleting_document_removes_its_vectors(self):
        with mock.patch("app.routers._shared.qa_kb_upload.delete_from_rag") as delete_from_rag:
            response = self.client.delete("/knowledge/files/guide.txt", params={"language": "zh"})

        self.assertEqual(response.status_code, 200)
        delete_from_rag.assert_called_once_with("hciot", "zh", "guide.txt")

    def test_editing_document_reindexes_new_content(self):
        with mock.patch("app.routers._shared.qa_kb_upload.sync_to_rag") as sync_to_rag:
            response = self.client.put(
                "/knowledge/files/guide.txt/content",
                params={"language": "zh"},
                json={"content": "new content"},
            )

        self.assertEqual(response.status_code, 200)
        sync_to_rag.assert_called_once_with("hciot", "zh", "guide.txt", b"new content")


if __name__ == "__main__":
    unittest.main()
