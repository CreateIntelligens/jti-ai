"""Regression coverage against a real MongoDB server.

Set JTI_INDEX_TEST_MONGO_URI to run these tests against a disposable database.
"""

import os
import uuid

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
