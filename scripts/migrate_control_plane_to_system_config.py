"""一次性遷移：控制面庫改名 gemini_notebook → system_config。

MongoDB 沒有 rename database，故以「複製集合 → 驗證 → （另行）切程式碼 → 刪舊庫」的
方式達成改名。本腳本只負責複製 + 驗證；刪除舊庫請在程式碼切換並確認線上正常後，
用 --drop-source 再跑一次（或手動 drop）。

搬移的集合（控制面三件）：users / prompts / api_keys。
空殼集合 sessions / conversations（0 筆）不搬，隨舊庫一併丟棄。

冪等：以各集合的自然鍵 upsert，重跑不會重複。

用法（在 backend 容器內，需 PYTHONPATH=/app）：
    python scripts/migrate_control_plane_to_system_config.py --dry-run
    python scripts/migrate_control_plane_to_system_config.py            # 複製 + 驗證
    python scripts/migrate_control_plane_to_system_config.py --drop-source  # 確認線上 OK 後刪舊庫
"""

import argparse
import sys

from app.services.db_names import CONTROL_PLANE_DB_NAME, LEGACY_CONTROL_PLANE_DB_NAME
from app.services.mongo_client import get_mongo_client

SOURCE_DB = LEGACY_CONTROL_PLANE_DB_NAME
TARGET_DB = CONTROL_PLANE_DB_NAME

# 集合 → 自然鍵（用於 upsert 與筆數驗證）
COLLECTIONS = {
    "users": "username",
    "prompts": "store_name",
    "api_keys": "key_hash",
}


def _copy(src_col, dst_col, key_field: str) -> int:
    count = 0
    for doc in src_col.find({}):
        key = doc.get(key_field)
        if key is None:
            dst_col.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        else:
            dst_col.replace_one({key_field: key}, doc, upsert=True)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--drop-source", action="store_true",
                        help="刪除舊庫（僅在程式碼已切換並確認線上正常後使用）")
    args = parser.parse_args()

    client = get_mongo_client().get_client()
    src = client[SOURCE_DB]
    dst = client[TARGET_DB]

    print(f"[scan] source={SOURCE_DB} target={TARGET_DB}")
    for col, key in COLLECTIONS.items():
        print(f"  {col}: {src[col].count_documents({})} 筆 (key={key})")

    if args.drop_source:
        # 安全檢查：目的庫每個集合筆數 >= 來源，才允許刪
        for col in COLLECTIONS:
            if dst[col].count_documents({}) < src[col].count_documents({}):
                print(f"[abort] {TARGET_DB}.{col} 筆數 < 來源，拒絕刪除。", file=sys.stderr)
                return 1
        client.drop_database(SOURCE_DB)
        print(f"[drop] 已刪除舊庫 {SOURCE_DB}。")
        return 0

    if args.dry_run:
        print("[dry-run] 不執行複製。")
        return 0

    for col, key in COLLECTIONS.items():
        n = _copy(src[col], dst[col], key)
        verify = dst[col].count_documents({})
        print(f"[copy] {col}: copied={n} → {TARGET_DB}.{col} now has {verify}")

    print("[done] 複製完成。請切換程式碼 DB 名指向 system_config 並驗證線上後，"
          "再以 --drop-source 刪舊庫。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
