#!/usr/bin/env python3
"""Atlas → DocumentDB 反向補資料 CLI(跳板/主庫恢復後執行)。

核心邏輯已抽到 app/services/db_sync/reverse.py,供後端 API 與本 CLI 共用。
本檔為薄 wrapper:解析 env、呼叫 run_reverse_sync、印出報表、回傳 exit code。

策略(衝突時 AWS 主庫為準):
    - 預設 $setOnInsert:只插入主庫不存在的文件,不覆蓋既有(= AWS 為主)。
    - MERGE_OVERWRITE=1 改為 $set 覆蓋,慎用。

環境變數:
    MERGE_SOURCE_URI   Atlas 連線字串(來源)。預設取 MONGODB_URI_FALLBACK。
    MERGE_TARGET_URI   DocumentDB 連線字串(目標)。預設取 MONGODB_URI。
    MERGE_TLS_CA_FILE  目標 TLS CA 路徑(DocumentDB 需要)。
    MERGE_OVERWRITE    設為 1 時用 $set 覆蓋(預設 0,只補不覆蓋)。
    MERGE_DRY_RUN      設為 1 時只報告不寫入。

用法:
    MERGE_DRY_RUN=1 python scripts/merge_atlas_to_documentdb.py   # 預演
    python scripts/merge_atlas_to_documentdb.py                   # 正式補
"""
from __future__ import annotations

import os
import sys

# 讓腳本能 import app 套件(專案根在 scripts/ 的上一層)。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.db_sync.forward import (  # noqa: E402
    SyncConfigError,
    SyncConnectionError,
)
from app.services.db_sync.reverse import run_reverse_sync  # noqa: E402


def main() -> int:
    overwrite = os.getenv("MERGE_OVERWRITE") == "1"
    dry_run = os.getenv("MERGE_DRY_RUN") == "1"

    prefix = "[DRY RUN] " if dry_run else ""
    mode = "覆蓋($set)" if overwrite else "只補不覆蓋($setOnInsert)"
    print(f"{prefix}Atlas → DocumentDB 反向補資料 [{mode}]")

    try:
        report = run_reverse_sync(dry_run=dry_run, overwrite=overwrite)
    except (SyncConfigError, SyncConnectionError) as e:
        print(f"❌ {e}")
        return 1

    for db_name, db_report in report["databases"].items():
        print(f"\n=== {db_name} ({len(db_report)} collections) ===")
        for col, stats in db_report.items():
            note = "覆蓋" if overwrite else "略過(已存在)"
            print(
                f"   {col}: 補入={stats['inserted']} "
                f"{note}={stats['skipped']} (鍵={stats['key']})"
            )

    print(
        f"\n{prefix}完成:補入 {report['total_inserted']}、"
        f"{'覆蓋' if overwrite else '略過'} {report['total_skipped']},"
        f"耗時 {report['elapsed_sec']}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
