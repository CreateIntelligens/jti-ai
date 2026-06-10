"""Question order must follow the merged (global index) order across split files.

Regression for: chat-side preset questions ignoring the admin drag order when a
topic is split into a main CSV plus per-image `_IMG_` CSVs.
"""
from unittest import mock
from unittest.mock import MagicMock

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers.hciot.knowledge import _sync_topic_questions_from_store
from app.services._shared.qa_kb.csv_utils import normalize_qa_csv_rows


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def test_sync_topic_questions_follows_global_index_across_split_files():
    fake_knowledge_store = MagicMock()
    # Main file holds indexes 1 and 6; image files hold 2 and 3.
    # Filename-ordered concatenation would yield Q1, Q6, Q2, Q3 (the bug).
    fake_knowledge_store.get_topic_csv_files.return_value = [
        {"filename": "門診.csv", "data": _csv("index,q,a,img\n1,Q1,A,\n6,Q6,A,\n")},
        {"filename": "門診_IMG_A0.csv", "data": _csv("index,q,a,img\n2,Q2,A,A0\n")},
        {"filename": "門診_IMG_A1.csv", "data": _csv("index,q,a,img\n3,Q3,A,A1\n")},
    ]

    fake_topic_store = MagicMock()
    fake_topic_store.get_topic.return_value = {
        "topic_id": "常見問題/門診",
        "labels": {"zh": "門診", "en": ""},
        "category_labels": {"zh": "常見問題", "en": ""},
        "questions": {"zh": ["Q1", "Q6", "Q2", "Q3"], "en": []},
        "hidden_questions": {"zh": [], "en": []},
    }

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_knowledge_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        result = _sync_topic_questions_from_store(
            language="zh",
            topic_id="常見問題/門診",
            topic_label="門診",
            category_label="常見問題",
        )

    assert result is True
    args, _ = fake_topic_store.update_topic.call_args
    _, update_data = args
    assert update_data["questions.zh"] == ["Q1", "Q2", "Q3", "Q6"]


def test_normalize_preserves_distinct_numeric_indexes():
    out = normalize_qa_csv_rows(_csv("index,q,a,img\n6,Q6,A,\n1,Q1,A,\n"))
    assert out is not None
    lines = out.decode("utf-8").strip().splitlines()
    # Sorted by index, original (gapped) values kept.
    assert lines[1].startswith("1,Q1")
    assert lines[2].startswith("6,Q6")


def test_normalize_renumbers_when_indexes_blank_or_duplicated():
    out = normalize_qa_csv_rows(_csv("index,q,a,img\n,QA,A,\n,QB,A,\n"))
    assert out is not None
    lines = out.decode("utf-8").strip().splitlines()
    assert lines[1].startswith("1,QA")
    assert lines[2].startswith("2,QB")

    out = normalize_qa_csv_rows(_csv("index,q,a,img\n1,QA,A,\n1,QB,A,\n"))
    assert out is not None
    lines = out.decode("utf-8").strip().splitlines()
    assert lines[1].startswith("1,QA")
    assert lines[2].startswith("2,QB")
