"""Atlas → DocumentDB 反向補資料(災後恢復用)。

主庫(DocumentDB,經跳板)不可用期間,app 會 fallback 寫入 Atlas。
待主庫恢復後,把「Atlas 有、DocumentDB 沒有」的資料補回主庫,
達成「fallback 期間資料不漏」。

策略(衝突時 AWS 主庫為準):
    - 預設 **$setOnInsert**:只插入主庫不存在的文件,**不覆蓋**主庫既有資料
      (主庫恢復後以主庫為準 = AWS 為主)。
    - overwrite=True 改為 $set(以 Atlas 值覆蓋主庫),慎用 —— 會違反「AWS 為主」。

何時執行:
    跳板/DocumentDB 恢復、app 切回主庫之後,執行一次(建議先 dry_run 預演)。

可由 CLI 腳本或後端 API 呼叫。``db_allowlist`` 讓呼叫端只補特定 app 的庫
(資料按 app 分 database,見 app/services/db_names.py)。
"""
from __future__ import annotations

import os
import time
from typing import Optional

from pymongo.errors import PyMongoError

from app.services.db_sync.common import (
    iterate_and_upsert,
    make_client,
)
from app.services.db_sync.forward import SyncConfigError, SyncConnectionError


def resolve_reverse_uris() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """回傳 (src_uri=Atlas, dst_uri=DocumentDB, ca_file),沿用既有 env 慣例。"""
    src_uri = os.getenv("MERGE_SOURCE_URI") or os.getenv("MONGODB_URI_FALLBACK")
    dst_uri = os.getenv("MERGE_TARGET_URI") or os.getenv("MONGODB_URI")
    ca_file = os.getenv("MERGE_TLS_CA_FILE") or os.getenv("SYNC_TLS_CA_FILE")
    return src_uri, dst_uri, ca_file


def run_reverse_sync(
    *,
    db_allowlist: Optional[set[str]] = None,
    dry_run: bool = False,
    overwrite: bool = False,
    src_uri: Optional[str] = None,
    dst_uri: Optional[str] = None,
    ca_file: Optional[str] = None,
) -> dict:
    """執行 Atlas → DocumentDB 反向補資料。

    Args:
        db_allowlist: 只補清單內的 database;None = 全部(仍排除系統庫)。
        dry_run: True 時只統計不寫入(預演)。
        overwrite: False(預設,AWS 為主)= $setOnInsert 只補不覆蓋;
                   True = $set 以 Atlas 覆蓋主庫(慎用)。
        src_uri/dst_uri/ca_file: 不傳則由 resolve_reverse_uris() 取 env。
                   注意:來源是 Atlas、目標是 DocumentDB(目標需 CA)。

    Returns:
        {
          "dry_run": bool,
          "overwrite": bool,
          "databases": {db: {col: {"inserted":int,"skipped":int,"key":str}}},
          "total_inserted": int,
          "total_skipped": int,  # overwrite=True 時為「覆蓋」筆數
          "elapsed_sec": float,
        }

    Raises:
        SyncConfigError: 來源/目標 URI 缺失。
        SyncConnectionError: 連線失敗。
    """
    if src_uri is None or dst_uri is None or ca_file is None:
        env_src, env_dst, env_ca = resolve_reverse_uris()
        src_uri = src_uri or env_src
        dst_uri = dst_uri or env_dst
        ca_file = ca_file if ca_file is not None else env_ca

    if not src_uri or not dst_uri:
        raise SyncConfigError(
            "需設定來源(MERGE_SOURCE_URI/MONGODB_URI_FALLBACK)與目標"
            "(MERGE_TARGET_URI/MONGODB_URI)"
        )

    update_op = "$set" if overwrite else "$setOnInsert"
    t0 = time.time()
    src = make_client(src_uri, None)        # Atlas 來源
    dst = make_client(dst_uri, ca_file)     # DocumentDB 目標(需 CA)

    try:
        src.admin.command("ping")
        dst.admin.command("ping")
    except PyMongoError as e:
        raise SyncConnectionError(f"連線失敗: {e}") from e

    report: dict = {
        "dry_run": dry_run,
        "overwrite": overwrite,
        "databases": {},
        "total_inserted": 0,
        "total_skipped": 0,
    }

    # upsert_collection 的 stats 對反向的語意:
    # - upserted = 主庫沒有、被補入的筆數。
    # - matched  = 主庫已有、業務鍵比對到的筆數
    #   (setOnInsert 時 = 略過不動;set 時 = 覆蓋,其中 modified = 真的改寫)。
    def record(_col: str, stats: dict) -> dict:
        report["total_inserted"] += stats["upserted"]
        report["total_skipped"] += stats["matched"]
        return {
            "inserted": stats["upserted"],
            "skipped": stats["matched"],
            "key": stats["key"],
        }

    try:
        report["databases"] = iterate_and_upsert(
            src, dst,
            db_allowlist=db_allowlist,
            build_update=lambda doc: {update_op: doc},
            dry_run=dry_run,
            record=record,
        )
    finally:
        src.close()
        dst.close()

    report["elapsed_sec"] = round(time.time() - t0, 1)
    return report
