"""Dry-run accounting for the primary → Atlas sync, against a real MongoDB server.

Set DB_SYNC_TEST_MONGO_URI to run these tests against a disposable database.
"""

import os
import uuid

import pytest
from pymongo import MongoClient


@pytest.fixture
def src_dst():
    uri = os.getenv("DB_SYNC_TEST_MONGO_URI")
    if not uri:
        pytest.skip("DB_SYNC_TEST_MONGO_URI is not set")

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    src_db = "test_sync_src_" + uuid.uuid4().hex
    dst_db = "test_sync_dst_" + uuid.uuid4().hex
    try:
        yield client[src_db]["sessions"], client[dst_db]["sessions"]
    finally:
        client.drop_database(src_db)
        client.drop_database(dst_db)
        client.close()


@pytest.mark.parametrize("batch_size", [2, 500])
def test_dry_run_counts_inserts_and_matches_without_writing(monkeypatch, src_dst, batch_size):
    from app.services.db_sync import common

    monkeypatch.setattr(common, "BATCH_SIZE", batch_size)
    src, dst = src_dst
    src.create_index("session_id", unique=True)
    src.insert_many([{"session_id": f"s{i}", "v": i} for i in range(5)])
    dst.insert_many([{"session_id": "s0", "v": 0}, {"session_id": "s3", "v": 99}])

    stats = common.upsert_collection(
        src, dst, build_update=lambda doc: {"$set": doc}, dry_run=True
    )

    assert stats["upserted"] == 3
    assert stats["matched"] == 2
    assert stats["modified"] == 0
    assert dst.count_documents({}) == 2
    assert dst.find_one({"session_id": "s3"})["v"] == 99


def test_dry_run_matches_real_run(src_dst):
    from app.services.db_sync import common

    src, dst = src_dst
    src.create_index("session_id", unique=True)
    src.insert_many([{"session_id": f"s{i}", "v": i} for i in range(4)])
    dst.insert_one({"session_id": "s1", "v": 1})

    preview = common.upsert_collection(src, dst, build_update=lambda doc: {"$set": doc}, dry_run=True)
    real = common.upsert_collection(src, dst, build_update=lambda doc: {"$set": doc}, dry_run=False)

    assert (preview["upserted"], preview["matched"]) == (real["upserted"], real["matched"])
