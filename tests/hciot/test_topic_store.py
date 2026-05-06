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
