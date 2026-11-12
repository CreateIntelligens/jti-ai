"""Regression coverage against a real MongoDB server.

Set JTI_INDEX_TEST_MONGO_URI to run these tests against a disposable database.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError


@pytest.mark.parametrize("existing_name", [None, "uniq_store_name_language_set_id_quiz_id"])
def test_quiz_results_indexes_survive_initialization(monkeypatch, existing_name):
    uri = os.getenv("JTI_INDEX_TEST_MONGO_URI")
    if not uri:
        pytest.skip("JTI_INDEX_TEST_MONGO_URI is not set")

    from app.services import mongo_client

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db_name = "test_quiz_indexes_" + uuid.uuid4().hex
    collection = client[db_name]["quiz_results"]
    keys = [("store_name", 1), ("language", 1), ("set_id", 1), ("quiz_id", 1)]
    try:
        if existing_name:
            collection.create_index(keys, unique=True, name=existing_name)
        collection.create_index("language")
        monkeypatch.setattr(mongo_client, "JTI_DB_NAME", db_name)
        instance = object.__new__(mongo_client.MongoDBClient)
        instance._client = client

        instance._initialize_collections()
        instance._initialize_collections()

        indexes = collection.index_information()
        assert "language_1" in indexes
        assert any(info.get("key") == keys and info.get("unique") for info in indexes.values())
        record = {"store_name": "test", "language": "zh", "set_id": "1", "quiz_id": "1"}
        collection.insert_one(record)
        with pytest.raises(DuplicateKeyError):
            collection.insert_one({key: value for key, value in record.items() if key != "_id"})
    finally:
        client.drop_database(db_name)
        client.close()


@pytest.fixture
def scratch_db(monkeypatch):
    uri = os.getenv("JTI_INDEX_TEST_MONGO_URI")
    if not uri:
        pytest.skip("JTI_INDEX_TEST_MONGO_URI is not set")

    from app.services import mongo_client

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db_name = "test_quiz_indexes_" + uuid.uuid4().hex
    monkeypatch.setattr(mongo_client, "JTI_DB_NAME", db_name)

    def initialize():
        instance = object.__new__(mongo_client.MongoDBClient)
        instance._client = client
        instance._initialize_collections()

    try:
        yield client[db_name], initialize
    finally:
        client.drop_database(db_name)
        client.close()


QUIZ_UNIQUE_KEYS = {
    "quiz_bank_questions": [("store_name", 1), ("language", 1), ("bank_id", 1), ("id", 1)],
    "quiz_bank_metadata": [("store_name", 1), ("language", 1), ("bank_id", 1)],
    "quiz_results": [("store_name", 1), ("language", 1), ("set_id", 1), ("quiz_id", 1)],
}


@pytest.mark.parametrize("collection_name", sorted(QUIZ_UNIQUE_KEYS))
def test_migrated_quiz_indexes_are_kept_as_is(scratch_db, collection_name):
    db, initialize = scratch_db
    collection = db[collection_name]
    collection.create_index(QUIZ_UNIQUE_KEYS[collection_name], unique=True, name="migrated_unique")
    collection.create_index("language")
    before = collection.index_information()

    initialize()
    initialize()

    after = collection.index_information()
    assert "migrated_unique" in after
    if collection_name != "quiz_bank_questions":
        assert "language_1" in after
    assert set(after) == set(before) | ({"store_name_1_language_1_bank_id_1"} if collection_name == "quiz_bank_questions" else set())


@pytest.mark.parametrize(
    ("collection_name", "legacy_keys"),
    [
        ("quiz_bank_questions", [("language", 1), ("bank_id", 1), ("id", 1)]),
        ("quiz_bank_metadata", [("language", 1), ("bank_id", 1)]),
        ("quiz_results", [("language", 1), ("set_id", 1), ("quiz_id", 1)]),
    ],
)
def test_legacy_unique_without_store_name_is_dropped(scratch_db, collection_name, legacy_keys):
    db, initialize = scratch_db
    collection = db[collection_name]
    collection.create_index(legacy_keys, unique=True, name="legacy_unique")

    initialize()

    indexes = collection.index_information()
    assert "legacy_unique" not in indexes
    assert any(
        info.get("key") == QUIZ_UNIQUE_KEYS[collection_name] and info.get("unique")
        for info in indexes.values()
    )
    base = {"store_name": "a", "language": "zh", "bank_id": "1", "id": "1", "set_id": "1", "quiz_id": "1"}
    collection.insert_one(dict(base))
    collection.insert_one({**base, "store_name": "b"})


def test_concurrent_initialization_ends_with_language_indexes(scratch_db):
    # 只驗證併發後的最終狀態；刪了又建回同名索引這種反覆刪建，這個測試看不出來。
    db, initialize = scratch_db
    initialize()

    with ThreadPoolExecutor(4) as pool:
        for future in [pool.submit(initialize) for _ in range(8)]:
            future.result()

    for collection_name in ("quiz_bank_metadata", "quiz_results"):
        assert "language_1" in db[collection_name].index_information()
