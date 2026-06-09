#!/usr/bin/env python3
"""DocumentDB → Atlas 全量單向同步（業務鍵 upsert，不刪除）。

用途：
    讓 Atlas 維持「接近最新」的資料副本，使得主庫(DocumentDB，經跳板)不可用時，
    app 能 fallback 到 Atlas 且資料不致大量落後。

策略（針對小資料量 ~數萬筆）：
    - 全量讀取 DocumentDB 每個 collection。
    - 以該 collection 的「unique 索引欄位」為業務鍵，upsert 到 Atlas。
    - 自動推導業務鍵：避免用 _id（ObjectId 兩庫各自生成，不可跨庫比對）。
    - 只 upsert、**不刪除** Atlas 既有文件 —— 保護 fallback 期間寫入 Atlas、
      但 DocumentDB 尚未擁有的資料（避免被同步覆蓋／刪除）。

不處理（刻意）：
    - 刪除同步：DocumentDB 刪掉的，Atlas 不會跟著刪（避免誤刪 fallback 資料）。
    - 反向（Atlas → DocumentDB）：fallback 期間資料的回補，見 merge_atlas_to_documentdb.py。

環境變數：
    SYNC_SOURCE_URI   DocumentDB 連線字串（來源）。預設取 MONGODB_URI。
    SYNC_TARGET_URI   Atlas 連線字串（目標）。預設取 MONGODB_URI_FALLBACK。
    SYNC_TLS_CA_FILE  來源 TLS CA 路徑（DocumentDB 需要），可選。
    SYNC_DRY_RUN      設為 1 時只報告不寫入。

用法：
    python scripts/sync_documentdb_to_atlas.py
    SYNC_DRY_RUN=1 python scripts/sync_documentdb_to_atlas.py   # 預演
"""
from __future__ import annotations

import os
import sys
import time

from pymongo.errors import PyMongoError

# 與反向補資料共用業務鍵推導，確保兩方向用相同鍵比對同一筆。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mongo_sync_common import (  # noqa: E402
    SYSTEM_DBS,
    make_client,
    upsert_collection,
)


def _sync_collection(src_col, dst_col, dry_run: bool) -> tuple[int, int, str]:
    """回傳 (upserted, matched, 用的業務鍵描述)。"""
    return upsert_collection(
        src_col,
        dst_col,
        build_update=lambda doc: {"$set": doc},
        dry_run=dry_run,
    )


def main() -> int:
    src_uri = os.getenv("SYNC_SOURCE_URI") or os.getenv("MONGODB_URI")
    dst_uri = os.getenv("SYNC_TARGET_URI") or os.getenv("MONGODB_URI_FALLBACK")
    ca_file = os.getenv("SYNC_TLS_CA_FILE")
    dry_run = os.getenv("SYNC_DRY_RUN") == "1"

    if not src_uri or not dst_uri:
        print("❌ 需設定來源(SYNC_SOURCE_URI/MONGODB_URI)與目標(SYNC_TARGET_URI/MONGODB_URI_FALLBACK)")
        return 1

    print(f"{'[DRY RUN] ' if dry_run else ''}DocumentDB → Atlas 全量同步")
    t0 = time.time()
    src = make_client(src_uri, ca_file)
    dst = make_client(dst_uri, None)

    try:
        src.admin.command("ping")
        dst.admin.command("ping")
    except PyMongoError as e:
        print(f"❌ 連線失敗: {e}")
        return 1

    total_up = total_match = 0
    for db_name in src.list_database_names():
        if db_name in SYSTEM_DBS:
            continue
        src_db, dst_db = src[db_name], dst[db_name]
        cols = src_db.list_collection_names()
        if cols:
            print(f"\n=== {db_name} ({len(cols)} collections) ===")
        for col in sorted(cols):
            up, match, key_desc = _sync_collection(src_db[col], dst_db[col], dry_run)
            total_up += up
            total_match += match
            print(f"   {col}: upsert新增={up} 既有更新={match} (鍵={key_desc})")

    print(
        f"\n{'[DRY RUN] ' if dry_run else ''}完成：新增 {total_up}、更新 {total_match}，"
        f"耗時 {time.time() - t0:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
