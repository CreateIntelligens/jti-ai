from unittest.mock import MagicMock

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.services.hciot.topic_store import HciotTopicStore


def make_store(
    collection: MagicMock,
    language: str = "zh",
    category_collection: MagicMock | None = None,
) -> HciotTopicStore:
    store = object.__new__(HciotTopicStore)
    store.language = language
    store.collection = collection
    store.category_collection = category_collection or MagicMock()
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


def test_upsert_topic_initializes_hidden_false_on_insert():
    collection = MagicMock()
    collection.find_one_and_update.return_value = None
    collection.count_documents.return_value = 0
    store = make_store(collection, "zh")

    store.upsert_topic(
        "faq/early-intervention",
        {
            "labels": {"zh": "早療", "en": ""},
            "category_labels": {"zh": "常見問題", "en": ""},
            "questions": {"zh": ["Q1"], "en": []},
        },
    )

    _, update = collection.find_one_and_update.call_args_list[-1].args[:2]
    assert update["$setOnInsert"]["hidden"] is False


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
    assert update["$set"]["hidden"] is False


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


def test_set_category_hidden_writes_category_meta_collection():
    collection = MagicMock()
    category_collection = MagicMock()
    category_collection.update_one.return_value = MagicMock(matched_count=1, upserted_id=None)
    store = make_store(collection, "zh", category_collection)

    result = store.set_category_hidden("ortho", True)

    assert result is True
    category_collection.update_one.assert_called_once()
    query, update = category_collection.update_one.call_args.args[:2]
    assert query == {"language": "zh", "category_id": "ortho"}
    assert update["$set"]["hidden"] is True
    assert update["$set"]["language"] == "zh"
    assert update["$set"]["category_id"] == "ortho"


def test_get_category_meta_returns_id_keyed_hidden_flags():
    collection = MagicMock()
    category_collection = MagicMock()
    category_collection.find.return_value = [
        {"category_id": "ortho", "hidden": True, "_id": "ignored"},
        {"category_id": "faq", "hidden": False},
    ]
    store = make_store(collection, "zh", category_collection)

    result = store.get_category_meta()

    category_collection.find.assert_called_once_with({"language": "zh"}, {"_id": 0})
    assert result == {
        "ortho": {"category_id": "ortho", "hidden": True},
        "faq": {"category_id": "faq", "hidden": False},
    }
