#!/usr/bin/env python3
"""DocumentDB → Atlas 全量單向同步 CLI(業務鍵 upsert,不刪除)。

核心邏輯已抽到 app/services/db_sync/forward.py,供後端 API 與本 CLI 共用。
本檔為薄 wrapper:解析 env、呼叫 run_forward_sync、印出報表、回傳 exit code。

環境變數:
    SYNC_SOURCE_URI   DocumentDB 連線字串(來源)。預設取 MONGODB_URI。
    SYNC_TARGET_URI   Atlas 連線字串(目標)。預設取 MONGODB_URI_FALLBACK。
    SYNC_TLS_CA_FILE  來源 TLS CA 路徑(DocumentDB 需要),可選。
    SYNC_DRY_RUN      設為 1 時只報告不寫入。

用法:
    python scripts/sync_documentdb_to_atlas.py
    SYNC_DRY_RUN=1 python scripts/sync_documentdb_to_atlas.py   # 預演
"""
from __future__ import annotations

import os
import sys

# 讓腳本能 import app 套件(專案根在 scripts/ 的上一層)。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.db_sync.forward import (  # noqa: E402
    SyncConfigError,
    SyncConnectionError,
    run_forward_sync,
)


def main() -> int:
    dry_run = os.getenv("SYNC_DRY_RUN") == "1"
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}DocumentDB → Atlas 全量同步")

    try:
        report = run_forward_sync(dry_run=dry_run)
    except SyncConfigError as e:
        print(f"❌ {e}")
        return 1
    except SyncConnectionError as e:
        print(f"❌ {e}")
        return 1

    for db_name, db_report in report["databases"].items():
        print(f"\n=== {db_name} ({len(db_report)} collections) ===")
        for col, stats in db_report.items():
            print(
                f"   {col}: upsert新增={stats['upserted']} "
                f"既有更新={stats['matched']} (鍵={stats['key']})"
            )

    print(
        f"\n{prefix}完成:新增 {report['total_upserted']}、"
        f"更新 {report['total_matched']},耗時 {report['elapsed_sec']}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
