from unittest.mock import MagicMock

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.services.hciot.topic_store import HciotTopicStore


def make_store(collection: MagicMock, language: str = "zh") -> HciotTopicStore:
    store = object.__new__(HciotTopicStore)
    store.language = language
    store.collection = collection
    return store


def test_list_topics_filters_chinese_documents_without_legacy_fallback():
    collection = MagicMock()
    collection.find.return_value.sort.return_value = []
    store = make_store(collection, "zh")

    store.list_topics()

    collection.find.assert_called_once_with({"language": "zh"}, {"_id": 0})


def test_list_topics_filters_english_documents_without_legacy_fallback():
    collection = MagicMock()
    collection.find.return_value.sort.return_value = []
    store = make_store(collection, "en")

    store.list_topics()

    collection.find.assert_called_once_with({"language": "en"}, {"_id": 0})


def test_english_upsert_targets_english_partition_only():
    collection = MagicMock()
    collection.find_one_and_update.return_value = None
    collection.count_documents.return_value = 0
    store = make_store(collection, "en")

    store.upsert_topic(
        "faq/early-intervention",
        {
            "labels": {"zh": "Early Intervention", "en": "Early Intervention"},
            "category_labels": {"zh": "FAQ", "en": "FAQ"},
        },
    )

    query, update = collection.find_one_and_update.call_args_list[-1].args[:2]
    assert query == {"topic_id": "faq/early-intervention", "language": "en"}
    assert update["$set"]["topic_id"] == "faq/early-intervention"
    assert update["$setOnInsert"]["language"] == "en"


def test_ensure_topic_initializes_hidden_questions():
    collection = MagicMock()
    collection.find_one.return_value = None
    collection.find_one_and_update.return_value = None
    collection.count_documents.return_value = 0
    store = make_store(collection, "zh")

    store.ensure_topic(
        "faq/early-intervention",
        labels={"zh": "早療", "en": "Early Intervention"},
        category_labels={"zh": "常見問題", "en": "FAQ"},
    )

    collection.find_one.assert_called_once_with({"topic_id": "faq/early-intervention", "language": "zh"}, {"_id": 0})
    _, update = collection.find_one_and_update.call_args_list[-1].args[:2]
    assert update["$set"]["hidden_questions"] == {"zh": [], "en": []}


def test_update_topic_saves_hidden_questions():
    collection = MagicMock()
    collection.update_one.return_value = MagicMock(matched_count=1)
    store = make_store(collection, "zh")

    store.update_topic(
        "faq/early-intervention",
        {"hidden_questions": {"zh": ["Q1"], "en": []}},
    )

    collection.update_one.assert_called_once()
    query, update = collection.update_one.call_args.args[:2]
    assert query == {"topic_id": "faq/early-intervention", "language": "zh"}
    assert update["$set"]["hidden_questions"] == {"zh": ["Q1"], "en": []}
