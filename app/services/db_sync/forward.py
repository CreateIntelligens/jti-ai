"""DocumentDB → Atlas 正向同步(業務鍵 upsert,不刪除)。

讓 Atlas 維持「接近最新」的資料副本,使得主庫(DocumentDB,經跳板)不可用時,
app 能 fallback 到 Atlas 且資料不致大量落後。

策略(針對小資料量 ~數萬筆):
    - 全量讀取來源每個(允許的) database 的 collection。
    - 以該 collection 的業務鍵 upsert 到目標庫(見 common.business_keys)。
    - 只 upsert、**不刪除** 目標庫既有文件 —— 保護 fallback 期間寫入 Atlas、
      但 DocumentDB 尚未擁有的資料(避免被同步覆蓋/刪除)。

刻意不處理:
    - 刪除同步:DocumentDB 刪掉的,Atlas 不會跟著刪。
    - 反向(Atlas → DocumentDB):見 scripts/merge_atlas_to_documentdb.py。

可由 CLI 腳本或後端 API 呼叫。``db_allowlist`` 讓呼叫端只同步特定 app 的庫
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


def resolve_forward_uris() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """回傳 (src_uri, dst_uri, ca_file),沿用既有 env 慣例。"""
    src_uri = os.getenv("SYNC_SOURCE_URI") or os.getenv("MONGODB_URI")
    dst_uri = os.getenv("SYNC_TARGET_URI") or os.getenv("MONGODB_URI_FALLBACK")
    ca_file = os.getenv("SYNC_TLS_CA_FILE")
    return src_uri, dst_uri, ca_file


class SyncConfigError(ValueError):
    """來源/目標連線字串缺失。"""


class SyncConnectionError(RuntimeError):
    """來源或目標連線(ping)失敗。"""


def run_forward_sync(
    *,
    db_allowlist: Optional[set[str]] = None,
    dry_run: bool = False,
    src_uri: Optional[str] = None,
    dst_uri: Optional[str] = None,
    ca_file: Optional[str] = None,
) -> dict:
    """執行 DocumentDB → Atlas 正向同步。

    Args:
        db_allowlist: 只同步清單內的 database;None = 全部(仍排除系統庫)。
        dry_run: True 時只統計不寫入。
        src_uri/dst_uri/ca_file: 不傳則由 resolve_forward_uris() 取 env。

    Returns:
        {
          "dry_run": bool,
          "databases": {db: {col: {"upserted":int,"matched":int,"key":str}}},
          "total_upserted": int,
          "total_matched": int,
          "elapsed_sec": float,
        }

    Raises:
        SyncConfigError: 來源/目標 URI 缺失。
        SyncConnectionError: 連線失敗。
    """
    if src_uri is None or dst_uri is None or ca_file is None:
        env_src, env_dst, env_ca = resolve_forward_uris()
        src_uri = src_uri or env_src
        dst_uri = dst_uri or env_dst
        ca_file = ca_file if ca_file is not None else env_ca

    if not src_uri or not dst_uri:
        raise SyncConfigError(
            "需設定來源(SYNC_SOURCE_URI/MONGODB_URI)與目標"
            "(SYNC_TARGET_URI/MONGODB_URI_FALLBACK)"
        )

    t0 = time.time()
    src = make_client(src_uri, ca_file)
    dst = make_client(dst_uri, None)

    try:
        src.admin.command("ping")
        dst.admin.command("ping")
    except PyMongoError as e:
        raise SyncConnectionError(f"連線失敗: {e}") from e

    report: dict = {
        "dry_run": dry_run,
        "databases": {},
        "total_upserted": 0,
        "total_modified": 0,
        "total_matched": 0,
    }

    def record(_col: str, stats: dict) -> dict:
        report["total_upserted"] += stats["upserted"]
        report["total_modified"] += stats["modified"]
        report["total_matched"] += stats["matched"]
        return {
            "upserted": stats["upserted"],
            "modified": stats["modified"],
            "matched": stats["matched"],
            "key": stats["key"],
        }

    try:
        report["databases"] = iterate_and_upsert(
            src, dst,
            db_allowlist=db_allowlist,
            build_update=lambda doc: {"$set": doc},
            dry_run=dry_run,
            record=record,
        )
    finally:
        src.close()
        dst.close()

    report["elapsed_sec"] = round(time.time() - t0, 1)
    return report
