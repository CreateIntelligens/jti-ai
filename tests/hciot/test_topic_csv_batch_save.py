"""Tests for the batch topic-CSV save endpoint (PUT /topic-csv-merged)."""
import unittest
from unittest import mock
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers._shared.qa_kb_router import QaKbRouterConfig, build_qa_kb_router
from app.utils import get_other_language

TOPIC_ID = "常見問題/門診"


def _build_client(knowledge_store: MagicMock, topic_store: MagicMock) -> TestClient:
    config = QaKbRouterConfig(
        tag="Test KB",
        app="hciot",
        knowledge_store_factory=lambda: knowledge_store,
        topic_store_factory=lambda language: topic_store,
        rag_source_type="hciot",
        invalidate_cache=lambda language=None: None,
        other_language=get_other_language,
    )
    with mock.patch(
        "app.routers._shared.qa_kb_router.require_kb_access",
        return_value=lambda: {"role": "admin"},
    ):
        router = build_qa_kb_router(config, include_knowledge=True, include_extract=False)
    app = FastAPI()
    app.include_router(router, prefix="/knowledge")
    return TestClient(app)


class TestTopicCsvBatchSave(unittest.TestCase):
    def setUp(self):
        self.knowledge_store = MagicMock()
        self.topic_store = MagicMock()
        self.client = _build_client(self.knowledge_store, self.topic_store)

        # Two existing CSV files belonging to the topic.
        self.files = {
            "a.csv": {
                "filename": "a.csv", "topic_id": TOPIC_ID, "data": b"index,q,a,img\n1,Q1,A,\n",
                "content_type": "text/csv", "editable": True,
                "topic_label": "門診", "category_label": "常見問題",
            },
            "b.csv": {
                "filename": "b.csv", "topic_id": TOPIC_ID, "data": b"index,q,a,img\n2,Q2,A,\n",
                "content_type": "text/csv", "editable": True,
                "topic_label": "門診", "category_label": "常見問題",
            },
        }
        self.knowledge_store.get_file.side_effect = lambda language, name: self.files.get(name)
        self.knowledge_store.update_file_content.return_value = True
        self.knowledge_store.delete_file.return_value = True
        self.knowledge_store.has_non_csv_files.return_value = False
        self.topic_store.get_topic.return_value = {
            "topic_id": TOPIC_ID,
            "questions": {"zh": ["Q1", "Q2"], "en": []},
            "hidden_questions": {"zh": [], "en": []},
        }

    def _put(self, payload: dict):
        return self.client.put(
            "/knowledge/topic-csv-merged",
            params={"topic_id": TOPIC_ID, "language": "zh"},
            json=payload,
        )

    def test_saves_all_files_and_syncs_topic_once(self):
        # After the save, the topic holds both files' rows in global order.
        self.knowledge_store.get_topic_csv_files.return_value = [
            {"filename": "a.csv", "data": b"index,q,a,img\n1,Q1,A,\n"},
            {"filename": "b.csv", "data": b"index,q,a,img\n2,Q2,A,\n"},
        ]
        response = self._put({
            "files": [
                {"filename": "a.csv", "content": "index,q,a,img\n1,Q1,A,\n"},
                {"filename": "b.csv", "content": "index,q,a,img\n2,Q2,A,\n"},
            ],
            "hidden_questions": ["Q2"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.knowledge_store.update_file_content.call_count, 2)
        # Topic sync ran exactly once and questions were rebuilt in merged order.
        sync_calls = [
            call for call in self.topic_store.update_topic.call_args_list
            if "questions.zh" in call.args[1]
        ]
        self.assertEqual(len(sync_calls), 1)
        self.assertEqual(sync_calls[0].args[1]["questions.zh"], ["Q1", "Q2"])
        # Hidden questions replaced (filtered to surviving questions).
        hidden_calls = [
            call for call in self.topic_store.update_topic.call_args_list
            if call.args[1].get("hidden_questions.zh") is not None and "questions.zh" not in call.args[1]
        ]
        self.assertEqual(len(hidden_calls), 1)
        self.assertEqual(hidden_calls[0].args[1]["hidden_questions.zh"], ["Q2"])

    def test_deletes_files_no_longer_holding_rows(self):
        self.knowledge_store.get_topic_csv_files.return_value = [
            {"filename": "a.csv", "data": b"index,q,a,img\n1,Q1,A,\n"},
        ]
        response = self._put({
            "files": [{"filename": "a.csv", "content": "index,q,a,img\n1,Q1,A,\n"}],
            "delete_files": ["b.csv"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.knowledge_store.delete_file.assert_called_once_with("zh", "b.csv")

    def test_rejects_file_from_another_topic(self):
        self.files["a.csv"]["topic_id"] = "別的/主題"
        response = self._put({
            "files": [{"filename": "a.csv", "content": "index,q,a,img\n1,Q1,A,\n"}],
        })
        self.assertEqual(response.status_code, 400)
        self.knowledge_store.update_file_content.assert_not_called()

    def test_rejects_unknown_file_before_writing_anything(self):
        response = self._put({
            "files": [
                {"filename": "a.csv", "content": "index,q,a,img\n1,Q1,A,\n"},
                {"filename": "missing.csv", "content": "index,q,a,img\n1,QX,A,\n"},
            ],
        })
        self.assertEqual(response.status_code, 404)
        # Validation happens before any write.
        self.knowledge_store.update_file_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
