"""DocumentDB ↔ Atlas 同步:可被後端 API 與 CLI 腳本共用的正式模組。

歷史上同步邏輯只存在於 scripts/ 下的 CLI 腳本;為了讓後端 endpoint 也能
觸發「指定 app 範圍」的同步,把核心邏輯抽到此 package:

- ``common``：跨庫業務鍵推導與批次 upsert(原 scripts/_mongo_sync_common.py)。
- ``forward``：DocumentDB → Atlas 正向同步(可指定 db_allowlist)。

scripts/ 下的腳本改為薄 wrapper 呼叫這裡,確保 CLI 與 API 行為一致。
"""
