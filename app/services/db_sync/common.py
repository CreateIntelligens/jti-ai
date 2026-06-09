"""DocumentDB ↔ Atlas 同步共用工具。

正向(forward)與反向(scripts/merge_atlas_to_documentdb.py)共用業務鍵推導
與連線建立,確保兩個方向用「相同的業務鍵」比對同一筆資料
(鍵不一致會導致補資料時誤判重複或重複插入)。

原本位於 scripts/_mongo_sync_common.py,為了讓後端 API 也能 import,
移到 app/services/db_sync/。CLI 腳本改為從這裡匯入。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

SYSTEM_DBS = {"admin", "local", "config"}
BATCH_SIZE = 500

# 明確業務鍵對照(當 collection 無 unique 索引、自動推導失敗時使用)。
# 以 collection 名稱比對(不含 DB 前綴)。避免退回 _id
# (ObjectId 兩庫各自生成、不可跨庫比對,會造成重複插入)。
EXPLICIT_KEYS: dict[str, list[str]] = {
    "conversations": ["session_id", "turn_number"],
    "hciot_categories": ["category_id", "language"],
    "hciot_topics": ["topic_id", "language"],
    # hciot_app.knowledge_files 未建 unique 索引(jti_app 的有),用相同業務鍵。
    "knowledge_files": ["namespace", "language", "filename"],
    "quizzes": ["session_id"],
}


def make_client(uri: str, ca_file: str | None = None) -> MongoClient:
    kwargs: dict[str, Any] = {"serverSelectionTimeoutMS": 10000}
    if ca_file:
        kwargs["tlsCAFile"] = ca_file
    return MongoClient(uri, **kwargs)


def business_keys(collection) -> list[str] | None:
    """推導業務鍵欄位(用於跨庫 upsert,取代不可跨庫的 _id)。

    優先序:
    1. collection 的 unique 索引欄位。
    2. EXPLICIT_KEYS 明確對照(處理非 unique 索引的 collection)。
    3. 都沒有 → None(呼叫端應退回 _id 並印警告)。
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
) -> dict:
    """以業務鍵批次 upsert collection。

    回傳 {"upserted":int, "modified":int, "matched":int, "key":str}:
    - upserted: 目標庫原本沒有、新插入的筆數。
    - modified: 目標庫已有、且**值真的被改寫**的筆數(MongoDB modified_count)。
    - matched:  目標庫已有、業務鍵**比對到**的筆數(含值沒變的;modified ⊆ matched)。
      ⚠ matched 不等於「有更新」——值相同時 matched 計入但 modified 不計。
    """
    keys = business_keys(src_col)
    key_desc = key_description(keys)
    ops: list[UpdateOne] = []
    upserted = modified = matched = 0

    def flush() -> None:
        nonlocal ops, upserted, modified, matched
        if not ops:
            return
        if dry_run:
            ops = []
            return
        try:
            res = dst_col.bulk_write(ops, ordered=False)
            upserted += res.upserted_count
            modified += res.modified_count
            matched += res.matched_count
        except BulkWriteError as e:
            upserted += e.details.get("nUpserted", 0)
            modified += e.details.get("nModified", 0)
            matched += e.details.get("nMatched", 0)
            print(f"      ⚠ bulk_write 部分失敗: {len(e.details.get('writeErrors', []))} 筆")
        ops = []

    for doc in src_col.find({}):
        if keys:
            flt = {key: doc.get(key) for key in keys}
        else:
            flt = {"_id": doc["_id"]}

        doc.pop("_id", None)  # 不跨庫帶 ObjectId,讓目標庫自行管理 _id
        ops.append(UpdateOne(flt, build_update(doc), upsert=True))
        if len(ops) >= BATCH_SIZE:
            flush()

    flush()
    return {
        "upserted": upserted,
        "modified": modified,
        "matched": matched,
        "key": key_desc,
    }


def iterate_and_upsert(
    src: MongoClient,
    dst: MongoClient,
    *,
    db_allowlist: set[str] | None,
    build_update: Callable[[dict], dict],
    dry_run: bool,
    record: Callable[[str, dict], None],
) -> dict[str, dict]:
    """掃描 src 每個(允許的)database 的 collection,逐一 upsert 到 dst。

    正向/反向同步共用此骨架(連線、ping、遍歷、close 由呼叫端負責)。差異
    只在 build_update(寫入操作)與 record(如何累計/命名統計),由參數注入。

    Args:
        src/dst: 已建立並 ping 過的來源/目標 client。
        db_allowlist: 只處理清單內的 database;None = 全部(仍排除系統庫)。
        build_update: 把來源文件轉成 update 文件(如 ``{"$set": doc}``)。
        dry_run: True 時 upsert_collection 只統計不寫入。
        record: 每個 collection 完成時呼叫 ``record(col, stats)``,由呼叫端
            決定如何寫進報表與累計總數。

    Returns:
        {db_name: {col: <呼叫端透過 record 寫入的條目>}}。
    """
    databases: dict[str, dict] = {}
    for db_name in src.list_database_names():
        if db_name in SYSTEM_DBS:
            continue
        if db_allowlist is not None and db_name not in db_allowlist:
            continue

        src_db, dst_db = src[db_name], dst[db_name]
        cols = sorted(src_db.list_collection_names())
        if not cols:
            continue

        db_report: dict = {}
        for col in cols:
            stats = upsert_collection(
                src_db[col],
                dst_db[col],
                build_update=build_update,
                dry_run=dry_run,
            )
            db_report[col] = record(col, stats)
        databases[db_name] = db_report
    return databases
