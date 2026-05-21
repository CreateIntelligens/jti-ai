from unittest import mock
from unittest.mock import MagicMock

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers.hciot.knowledge import _sync_topic_questions_from_store


def test_sync_topic_questions_cleanup_obsolete_hidden_questions():
    fake_knowledge_store = MagicMock()
    # CSV has Q1 and Q3. Q2 is obsolete/removed from CSV.
    csv_bytes = b"index,q,a,img\n1,Q1,A1,\n2,Q3,A3,\n"
    fake_knowledge_store.get_topic_csv_files.return_value = [
        {"filename": "prp.csv", "data": csv_bytes}
    ]

    fake_topic_store = MagicMock()
    # Existing topic has Q1 and Q2 hidden.
    fake_topic_store.get_topic.return_value = {
        "topic_id": "ortho/prp",
        "labels": {"zh": "PRP", "en": ""},
        "category_labels": {"zh": "骨科", "en": ""},
        "questions": {"zh": ["Q1", "Q2"], "en": []},
        "hidden_questions": {"zh": ["Q1", "Q2"], "en": []},
    }

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_knowledge_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        result = _sync_topic_questions_from_store(
            language="zh",
            topic_id="ortho/prp",
            topic_label="PRP",
            category_label="骨科",
        )

    assert result is True
    fake_topic_store.update_topic.assert_called_once()

    args, _ = fake_topic_store.update_topic.call_args
    topic_id, update_data = args
    assert topic_id == "ortho/prp"

    # Q2 was hidden but is not in current questions, so it must be removed.
    # Q1 was hidden and is still in current questions, so it must remain.
    assert update_data["questions.zh"] == ["Q1", "Q3"]
    assert update_data["hidden_questions.zh"] == ["Q1"]


def test_sync_topic_questions_handles_missing_hidden_questions_field():
    fake_knowledge_store = MagicMock()
    csv_bytes = b"index,q,a,img\n1,Q1,A1,\n"
    fake_knowledge_store.get_topic_csv_files.return_value = [
        {"filename": "prp.csv", "data": csv_bytes}
    ]

    fake_topic_store = MagicMock()
    fake_topic_store.get_topic.return_value = {
        "topic_id": "ortho/prp",
        "labels": {"zh": "PRP", "en": ""},
        "category_labels": {"zh": "骨科", "en": ""},
        "questions": {"zh": ["Q1"], "en": []},
    }

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_knowledge_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        result = _sync_topic_questions_from_store(
            language="zh",
            topic_id="ortho/prp",
            topic_label="PRP",
            category_label="骨科",
        )

    assert result is True
    fake_topic_store.update_topic.assert_called_once()
    args, _ = fake_topic_store.update_topic.call_args
    topic_id, update_data = args
    assert update_data["hidden_questions.zh"] == []


def test_sync_topic_questions_writes_explicit_hidden_questions():
    """B-2: hidden_questions passed at upload time is written atomically."""
    fake_knowledge_store = MagicMock()
    csv_bytes = b"index,q,a,img\n1,Q1,A1,\n2,Q2,A2,\n3,Q3,A3,\n"
    fake_knowledge_store.get_topic_csv_files.return_value = [
        {"filename": "prp.csv", "data": csv_bytes}
    ]

    fake_topic_store = MagicMock()
    # Topic already exists; its previous hidden_questions must be overridden by
    # the explicit list, not merged.
    fake_topic_store.get_topic.return_value = {
        "topic_id": "ortho/prp",
        "labels": {"zh": "PRP", "en": ""},
        "category_labels": {"zh": "骨科", "en": ""},
        "questions": {"zh": ["Q1"], "en": []},
        "hidden_questions": {"zh": ["Q1"], "en": []},
    }

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_knowledge_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        result = _sync_topic_questions_from_store(
            language="zh",
            topic_id="ortho/prp",
            topic_label="PRP",
            category_label="骨科",
            # "Q9" does not exist in the CSV and must be dropped by the
            # intersection; "Q1" was previously hidden but is now visible.
            hidden_questions=["Q2", "Q9"],
        )

    assert result is True
    fake_topic_store.update_topic.assert_called_once()
    args, _ = fake_topic_store.update_topic.call_args
    _, update_data = args
    assert update_data["questions.zh"] == ["Q1", "Q2", "Q3"]
    assert update_data["hidden_questions.zh"] == ["Q2"]


def test_sync_topic_questions_creates_topic_with_explicit_hidden_questions():
    """B-2: a brand-new topic carries the explicit hidden_questions on upsert."""
    fake_knowledge_store = MagicMock()
    csv_bytes = b"index,q,a,img\n1,Q1,A1,\n2,Q2,A2,\n"
    fake_knowledge_store.get_topic_csv_files.return_value = [
        {"filename": "prp.csv", "data": csv_bytes}
    ]

    fake_topic_store = MagicMock()
    fake_topic_store.get_topic.return_value = None  # topic does not exist yet

    with mock.patch("app.routers.hciot.knowledge.get_hciot_knowledge_store", return_value=fake_knowledge_store), \
         mock.patch("app.routers.hciot.knowledge.get_hciot_topic_store", return_value=fake_topic_store):
        result = _sync_topic_questions_from_store(
            language="zh",
            topic_id="ortho/prp",
            topic_label="PRP",
            category_label="骨科",
            hidden_questions=["Q2"],
        )

    assert result is True
    fake_topic_store.upsert_topic.assert_called_once()
    args, _ = fake_topic_store.upsert_topic.call_args
    _, payload = args
    assert payload["questions"]["zh"] == ["Q1", "Q2"]
    assert payload["hidden_questions"]["zh"] == ["Q2"]
    assert payload["hidden_questions"]["en"] == []
