"""一次性遷移：將 general 的 session / conversation 從 jti_app 搬到 general_app。

背景：general（動態知識庫，如 fish 等店）的對話 session 與紀錄過去寄生於
jti_app，與 JTI 測驗 session 混在同一集合。本腳本將其搬到獨立的 general_app 庫。

判別規則（與程式碼一致）：
- sessions：``metadata.store_name`` 存在 → 屬於 general
- conversations：``mode == "general"`` → 屬於 general

流程：copy → 驗證筆數 → 再從來源刪除（可用 --dry-run 只看不搬，--no-delete 只搬不刪）。
冪等：以 session_id / _id upsert，重跑不會重複。

用法（在 backend 容器內執行）：
    python scripts/migrate_general_to_general_app.py --dry-run
    python scripts/migrate_general_to_general_app.py            # 實際搬移並刪除來源
    python scripts/migrate_general_to_general_app.py --no-delete  # 只搬不刪
"""

import argparse
import sys

from app.services.mongo_client import get_mongo_db
from app.services.db_names import JTI_DB_NAME, GENERAL_DB_NAME

SESSION_FILTER = {"metadata.store_name": {"$exists": True}}
CONV_FILTER = {"mode": "general"}


def _copy_collection(src, dst, key_field: str, doc_filter: dict) -> int:
    """以 key_field 為鍵，把符合 doc_filter 的文件 upsert 到 dst。回傳處理筆數。"""
    count = 0
    for doc in src.find(doc_filter):
        key = doc.get(key_field)
        if key is None:
            # conversations 無自訂鍵時退回 _id
            dst.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        else:
            dst.replace_one({key_field: key}, doc, upsert=True)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只統計，不搬移不刪除")
    parser.add_argument("--no-delete", action="store_true", help="搬移但不刪除來源")
    args = parser.parse_args()

    src_db = get_mongo_db(JTI_DB_NAME)
    dst_db = get_mongo_db(GENERAL_DB_NAME)

    src_sessions = src_db["sessions"]
    src_convs = src_db["conversations"]

    n_sessions = src_sessions.count_documents(SESSION_FILTER)
    n_convs = src_convs.count_documents(CONV_FILTER)
    print(f"[scan] general sessions in {JTI_DB_NAME}: {n_sessions}")
    print(f"[scan] general conversations in {JTI_DB_NAME}: {n_convs}")

    if args.dry_run:
        print("[dry-run] 不執行搬移/刪除。")
        return 0

    copied_s = _copy_collection(src_sessions, dst_db["sessions"], "session_id", SESSION_FILTER)
    copied_c = _copy_collection(src_convs, dst_db["conversations"], "_id", CONV_FILTER)
    print(f"[copy] sessions copied: {copied_s} | conversations copied: {copied_c}")

    # 驗證目的地筆數 >= 來源筆數
    dst_s = dst_db["sessions"].count_documents(SESSION_FILTER)
    dst_c = dst_db["conversations"].count_documents(CONV_FILTER)
    print(f"[verify] {GENERAL_DB_NAME} general sessions: {dst_s} | conversations: {dst_c}")
    if dst_s < n_sessions or dst_c < n_convs:
        print("[abort] 目的地筆數小於來源，停止刪除以策安全。", file=sys.stderr)
        return 1

    if args.no_delete:
        print("[no-delete] 搬移完成，保留來源資料。")
        return 0

    del_s = src_sessions.delete_many(SESSION_FILTER).deleted_count
    del_c = src_convs.delete_many(CONV_FILTER).deleted_count
    print(f"[cleanup] deleted from {JTI_DB_NAME} → sessions: {del_s} | conversations: {del_c}")
    print("[done] 遷移完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
