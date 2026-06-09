#!/usr/bin/env python3
"""Atlas → DocumentDB 反向補資料（跳板/主庫恢復後執行）。

用途：
    主庫(DocumentDB，經跳板)不可用期間，app 會 fallback 寫入 Atlas。
    待主庫恢復後，執行本腳本把「Atlas 有、DocumentDB 沒有」的資料補回主庫，
    達成「fallback 期間資料不漏」。

策略（保守，預設只補不覆蓋）：
    - 以業務鍵比對（與正向同步共用 _mongo_sync_common，確保鍵一致）。
    - 預設 **$setOnInsert**：只插入 DocumentDB 不存在的文件，
      **不覆蓋** DocumentDB 既有資料（主庫恢復後以主庫為準）。
    - MERGE_OVERWRITE=1 可改為 $set（覆蓋），慎用：會以 Atlas 值蓋過主庫。

何時執行：
    跳板/DocumentDB 恢復、app 切回主庫之後，手動執行一次。
    建議先 MERGE_DRY_RUN=1 預演，確認補入筆數合理再正式跑。

環境變數：
    MERGE_SOURCE_URI   Atlas 連線字串（來源）。預設取 MONGODB_URI_FALLBACK。
    MERGE_TARGET_URI   DocumentDB 連線字串（目標）。預設取 MONGODB_URI。
    MERGE_TLS_CA_FILE  目標 TLS CA 路徑（DocumentDB 需要）。
    MERGE_OVERWRITE    設為 1 時用 $set 覆蓋（預設 0，只補不覆蓋）。
    MERGE_DRY_RUN      設為 1 時只報告不寫入。

用法：
    MERGE_DRY_RUN=1 python scripts/merge_atlas_to_documentdb.py   # 預演
    python scripts/merge_atlas_to_documentdb.py                   # 正式補
"""
from __future__ import annotations

import os
import sys
import time

from pymongo.errors import PyMongoError

# 與正向同步共用業務鍵推導，確保兩方向用相同鍵比對同一筆。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mongo_sync_common import (  # noqa: E402
    SYSTEM_DBS,
    make_client,
    upsert_collection,
)


def _merge_collection(src_col, dst_col, *, overwrite: bool, dry_run: bool) -> tuple[int, int, str]:
    """回傳 (inserted, matched, 業務鍵描述)。

    overwrite=False（預設）：$setOnInsert，只補主庫沒有的，不動既有。
    overwrite=True：$set，以 Atlas 值覆蓋主庫（慎用）。
    """
    update_op = "$set" if overwrite else "$setOnInsert"
    return upsert_collection(
        src_col,
        dst_col,
        build_update=lambda doc: {update_op: doc},
        dry_run=dry_run,
    )


def main() -> int:
    src_uri = os.getenv("MERGE_SOURCE_URI") or os.getenv("MONGODB_URI_FALLBACK")
    dst_uri = os.getenv("MERGE_TARGET_URI") or os.getenv("MONGODB_URI")
    ca_file = os.getenv("MERGE_TLS_CA_FILE")
    overwrite = os.getenv("MERGE_OVERWRITE") == "1"
    dry_run = os.getenv("MERGE_DRY_RUN") == "1"

    if not src_uri or not dst_uri:
        print("❌ 需設定來源(MERGE_SOURCE_URI/MONGODB_URI_FALLBACK)與目標(MERGE_TARGET_URI/MONGODB_URI)")
        return 1

    mode = "覆蓋($set)" if overwrite else "只補不覆蓋($setOnInsert)"
    print(f"{'[DRY RUN] ' if dry_run else ''}Atlas → DocumentDB 反向補資料 [{mode}]")
    t0 = time.time()
    src = make_client(src_uri, None)        # Atlas 來源
    dst = make_client(dst_uri, ca_file)     # DocumentDB 目標（需 CA）

    try:
        src.admin.command("ping")
        dst.admin.command("ping")
    except PyMongoError as e:
        print(f"❌ 連線失敗: {e}")
        return 1

    total_ins = total_match = 0
    for db_name in src.list_database_names():
        if db_name in SYSTEM_DBS:
            continue
        src_db, dst_db = src[db_name], dst[db_name]
        cols = src_db.list_collection_names()
        if cols:
            print(f"\n=== {db_name} ({len(cols)} collections) ===")
        for col in sorted(cols):
            ins, match, key_desc = _merge_collection(
                src_db[col], dst_db[col], overwrite=overwrite, dry_run=dry_run
            )
            total_ins += ins
            total_match += match
            note = "覆蓋" if overwrite else "略過(已存在)"
            print(f"   {col}: 補入={ins} {note}={match} (鍵={key_desc})")

    print(
        f"\n{'[DRY RUN] ' if dry_run else ''}完成：補入 {total_ins}、"
        f"{'覆蓋' if overwrite else '略過'} {total_match}，耗時 {time.time() - t0:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
