# DocumentDB ↔ Atlas 同步與備援

ai360 km 主資料庫為 **AWS DocumentDB**（經 `db-tunnel` 容器連線），
**Atlas** 作為備援，達成「主庫不可用時頂上、且資料不漏」。

本目錄含三個檔案：

| 檔案 | 方向 | 何時用 |
|---|---|---|
| `sync_documentdb_to_atlas.py` | DocumentDB → Atlas | 平常定時（cron），讓 Atlas 保持最新 |
| `merge_atlas_to_documentdb.py` | Atlas → DocumentDB | 主庫恢復後，把 fallback 期間資料補回 |
| `_mongo_sync_common.py` | （共用） | 業務鍵推導，兩腳本共用，勿單獨執行 |

---

## 運作全貌

```
平常：
   app 寫 → DocumentDB（主）
   cron 每日 → sync_documentdb_to_atlas.py → Atlas 保持接近最新

主庫/跳板掛掉：
   app 啟動偵測連不到主庫 → fallback 連 Atlas（已有近期資料）→ 服務頂上
   app 寫 → 寫進 Atlas

主庫恢復：
   重啟 app → 連回 DocumentDB（主）
   執行 merge_atlas_to_documentdb.py → 把 fallback 期間寫入 Atlas 的資料補回主庫
```

fallback 由 app 端 `resolve_mongodb_uri()` 處理（啟動時判斷一次，見
`app/services/mongo_client.py`）。同步/補資料則由本目錄腳本處理。

---

## 設計重點

- **業務鍵 upsert**：以各 collection 的 unique 索引（或 `_mongo_sync_common.EXPLICIT_KEYS`
  明確對照）為鍵，**不使用 `_id`**（ObjectId 兩庫各自生成、不可跨庫比對，否則會重複插入）。
- **正向只 upsert、不刪除**：避免覆蓋／刪除 fallback 期間寫入 Atlas、但主庫尚無的資料。
- **反向預設只補不覆蓋**（`$setOnInsert`）：主庫恢復後以主庫為準，只補主庫缺的。
- 新增 collection 若無 unique 索引，需在 `_mongo_sync_common.EXPLICIT_KEYS` 補業務鍵，
  否則腳本會印 `⚠_id(無業務鍵,可能重複)` 警告。

---

## 平常：定時同步（cron）

腳本需要連線字串環境變數。從 `.env` 取用，或直接帶入。

```bash
# 範例：每日 03:00 跑全量同步（DocumentDB → Atlas）
# 需在能連到 db-tunnel:27017（或直接連 DocumentDB）的環境執行。
0 3 * * *  cd /path/to/ai360-km && \
  SYNC_SOURCE_URI="$MONGODB_URI" \
  SYNC_TARGET_URI="$MONGODB_URI_FALLBACK" \
  SYNC_TLS_CA_FILE=/app/global-bundle.pem \
  python scripts/sync_documentdb_to_atlas.py >> logs/db_sync.log 2>&1
```

預演（不寫入）：
```bash
SYNC_DRY_RUN=1 python scripts/sync_documentdb_to_atlas.py
```

資料量小（~數萬筆）時全量同步僅數十秒，每日一次即可；要更即時可調高頻率。

---

## 主庫恢復後：補回 fallback 資料

主庫/跳板修復、app 已切回主庫之後，**手動執行一次**：

```bash
# 先預演，確認補入筆數合理
MERGE_DRY_RUN=1 \
  MERGE_SOURCE_URI="$MONGODB_URI_FALLBACK" \
  MERGE_TARGET_URI="$MONGODB_URI" \
  MERGE_TLS_CA_FILE=/app/global-bundle.pem \
  python scripts/merge_atlas_to_documentdb.py

# 確認無誤後正式補（移除 MERGE_DRY_RUN）
MERGE_SOURCE_URI="$MONGODB_URI_FALLBACK" \
  MERGE_TARGET_URI="$MONGODB_URI" \
  MERGE_TLS_CA_FILE=/app/global-bundle.pem \
  python scripts/merge_atlas_to_documentdb.py
```

- 預設 `$setOnInsert`：只補主庫沒有的，不覆蓋既有。
- 確需以 Atlas 值覆蓋主庫時加 `MERGE_OVERWRITE=1`（慎用）。

---

## 環境變數總表

### sync_documentdb_to_atlas.py
| 變數 | 預設 | 說明 |
|---|---|---|
| `SYNC_SOURCE_URI` | `MONGODB_URI` | 來源（DocumentDB）|
| `SYNC_TARGET_URI` | `MONGODB_URI_FALLBACK` | 目標（Atlas）|
| `SYNC_TLS_CA_FILE` | — | 來源 TLS CA（DocumentDB 需要）|
| `SYNC_DRY_RUN` | — | `1` 只報告不寫入 |

### merge_atlas_to_documentdb.py
| 變數 | 預設 | 說明 |
|---|---|---|
| `MERGE_SOURCE_URI` | `MONGODB_URI_FALLBACK` | 來源（Atlas）|
| `MERGE_TARGET_URI` | `MONGODB_URI` | 目標（DocumentDB）|
| `MERGE_TLS_CA_FILE` | — | 目標 TLS CA（DocumentDB 需要）|
| `MERGE_OVERWRITE` | `0` | `1` 用 `$set` 覆蓋（慎用）|
| `MERGE_DRY_RUN` | — | `1` 只報告不寫入 |

---

## 限制（刻意取捨）

- **刪除不同步**：主庫刪掉的資料，同步不會在 Atlas 刪除（避免誤刪 fallback 資料）。
- **執行中不切換**：fallback 為啟動時判斷一次；主庫跑到一半掛掉需重啟 app 才會切。
- **fallback 期間設定類資料（users/api_keys/knowledge_stores）若有改動**，補回時若與主庫衝突，
  預設 `$setOnInsert` 會略過（不覆蓋主庫）。這類資料建議避免在 fallback 期間變更。
- 向量資料存於本地 LanceDB，不在本同步範圍。
