"""DocumentDB ↔ Atlas 同步腳本共用工具。

正向（sync_documentdb_to_atlas）與反向（merge_atlas_to_documentdb）共用
業務鍵推導與連線建立，確保兩個方向用「相同的業務鍵」比對同一筆資料
（鍵不一致會導致補資料時誤判重複或重複插入）。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

SYSTEM_DBS = {"admin", "local", "config"}
BATCH_SIZE = 500

# 明確業務鍵對照（當 collection 無 unique 索引、自動推導失敗時使用）。
# 以 collection 名稱比對（不含 DB 前綴）。避免退回 _id
# （ObjectId 兩庫各自生成、不可跨庫比對，會造成重複插入）。
EXPLICIT_KEYS: dict[str, list[str]] = {
    "conversations": ["session_id", "turn_number"],
    "hciot_categories": ["category_id", "language"],
    "hciot_topics": ["topic_id", "language"],
    # hciot_app.knowledge_files 未建 unique 索引（jti_app 的有），用相同業務鍵。
    "knowledge_files": ["namespace", "language", "filename"],
    "quizzes": ["session_id"],
}


def make_client(uri: str, ca_file: str | None = None) -> MongoClient:
    kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 10000}
    if ca_file:
        kwargs["tlsCAFile"] = ca_file
    return MongoClient(uri, **kwargs)


def business_keys(collection) -> list[str] | None:
    """推導業務鍵欄位（用於跨庫 upsert，取代不可跨庫的 _id）。

    優先序：
    1. collection 的 unique 索引欄位。
    2. EXPLICIT_KEYS 明確對照（處理非 unique 索引的 collection）。
    3. 都沒有 → None（呼叫端應退回 _id 並印警告）。
    """
    try:
        for name, info in collection.index_information().items():
            if name == "_id_":
                continue
            if info.get("unique"):
                return [field for field, _direction in info["key"]]
    except PyMongoError:
        pass
    return EXPLICIT_KEYS.get(collection.name)


def key_description(keys: list[str] | None) -> str:
    if keys:
        return "+".join(keys)
    return "⚠_id(無業務鍵,可能重複)"


def upsert_collection(
    src_col,
    dst_col,
    *,
    build_update: Callable[[dict], dict],
    dry_run: bool,
) -> tuple[int, int, str]:
    """以業務鍵批次 upsert collection，回傳 (upserted, matched, key_desc)。"""
    keys = business_keys(src_col)
    key_desc = key_description(keys)
    ops: list[UpdateOne] = []
    upserted = matched = 0

    def flush() -> None:
        nonlocal ops, upserted, matched
        if not ops:
            return
        if dry_run:
            ops = []
            return
        try:
            res = dst_col.bulk_write(ops, ordered=False)
            upserted += res.upserted_count
            matched += res.matched_count
        except BulkWriteError as e:
            upserted += e.details.get("nUpserted", 0)
            matched += e.details.get("nMatched", 0)
            print(f"      ⚠ bulk_write 部分失敗: {len(e.details.get('writeErrors', []))} 筆")
        ops = []

    for doc in src_col.find({}):
        if keys:
            flt = {key: doc.get(key) for key in keys}
        else:
            flt = {"_id": doc["_id"]}

        doc.pop("_id", None)  # 不跨庫帶 ObjectId，讓目標庫自行管理 _id
        ops.append(UpdateOne(flt, build_update(doc), upsert=True))
        if len(ops) >= BATCH_SIZE:
            flush()

    flush()
    return upserted, matched, key_desc
