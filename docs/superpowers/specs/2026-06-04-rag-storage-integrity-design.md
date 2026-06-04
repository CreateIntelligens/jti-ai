# JTAI RAG 儲存完整性與備份同步設計文件

- **日期**：2026-06-04（v1 初版）
- **狀態**：Draft（問題已確認，修法待排程）
- **分支**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **預期執行者**：Claude（可接受其他 AI 監督檢視）
- **相關文件**：[app↔key 綁定](2026-06-02-app-key-map.md)、[app/store 層級與 scope](2026-06-02-app-store-hierarchy-and-scope.md)

---

## 1. 背景與動機

排查「general 知識庫（寶島釣魚）main 抓不到、Mongo 滿了」時，連帶挖出 RAG 儲存層的多個結構性漏洞。本文件記錄問題根因與修復方向，避免邊清邊忘、避免重複踩坑。

### 現況事實（2026-06-04 排查所得）

兩個儲存，本質不同：

| | LanceDB | Mongo `vector_backup` |
|---|---|---|
| 位置 | **本地檔案**，每部署各自 `data/lancedb/` | Mongo（兩部署共用同一個 `jti_app` DB）|
| 共用 | ❌ main 一份、worktree 一份，獨立 | ✅ 共用 |
| 角色 | **檢索主儲存** | 備份桶（**目前只寫不讀**）|

排查當下實測：

- main（8913）LanceDB：**774,652 筆**，其中 hciot **774,247 筆**爆量；distinct file_id 僅 262。
- worktree（8914）LanceDB：1,280 筆，健康。
- 爆量來源：壓測檔 `QA254-*`（單檔最高 30 萬筆），透過 API 反覆灌入。
- `vector_backup`：排查中已被手動清空（0 筆）。

---

## 2. 漏洞清單（按嚴重度）

### 漏洞 1 — 上傳可無限灌爆 LanceDB，孤兒無法回收（高）

- 任何走 `sync_to_rag` 的上傳直接進 LanceDB：**無大小上限、無筆數上限、無速率限制、無測試資料隔離**。
- `index_single_file` 的「先刪後插」(`backfill.py:354-356`) 是**按單一檔名 replace**，只處理「呼叫端指定的那個檔」。
- `_prune_orphans`(`backfill.py:259`) 只在 `run_backfill` 跑某 source_type 時、針對該批 `live_files`（來自檔案系統清單）比對清除。
- **透過 API 灌入、且不在檔案系統清單裡的孤兒（如 `QA254-*`）兩條路徑都碰不到 → 永遠清不掉。** 這就是 77 萬筆躺著沒人管的原因。
- 重開**無法**解決：backfill 找不到孤兒的來源檔，不會 replace 也不會刪；若壓測檔恰好落地在 `data/`，反而會再 index 一次疊加。

### 漏洞 2 — `vector_backup` 只寫不讀，是假備份（高）

- `MongoDBBackup` 只有 `sync_to_mongodb`(寫)、`delete_by_file`、`list_file_ids`，**沒有 restore**。
- 名為 backup，實際從不回灌 LanceDB。
- 後果：**general 動態上傳的資料（如釣魚）只活在本地 LanceDB**。LanceDB 一掉或換部署即**永久消失**，「雲端備份」救不回（沒 restore）。
- 這也是「main 抓不到釣魚」的根：main 從沒被餵過、也沒機制從 Mongo 拉回。

### 漏洞 3 — 多部署資料不一致，無單一真相來源（中高）

- main / worktree 各一份 LanceDB，內容天差地遠；Mongo 共用卻不同步。
- 「上傳一次、到處同步」是預期心智模型，但**未實作**：
  - jti/hciot 靠 git 內檔案，各部署啟動 backfill 各自重建 → 碰巧到處都有（非真同步，是各自重算）。
  - general 不在 git、backfill 不掃它、Mongo 不 restore → 完全沒同步。

### 漏洞 4 — `vector_backup` db_name 寫死 `jti_app`（中）

- `get_mongodb_backup()`(`mongodb_backup.py:71`) 寫死 `db_name="jti_app"`，全域單例。
- 不論 jti / hciot / general 上傳，向量全混進 `jti_app.vector_backup`，靠 `source_type` 欄位區分。
- 與系統其他處（session/設定按 `jti_app` / `hciot_app` 分流）**不一致**，命名誤導排查。

---

## 3. 修復方向（優先序）

### 步驟 0 — 止血：清掉壓測孤兒（不改架構）

- 按 file_id 精準刪除 main LanceDB 與 Mongo 中的 `QA254-*`（`delete_by_file`），確保健康的 hciot (868 筆)、釣魚 (195 筆) 與 jti (210 筆) 不受影響。
- 純清理，先讓系統恢復正常。

### 步驟 1 — 補真備份與還原 (Restore) 機制（解漏洞 2、3）

- **新增還原邏輯**：`MongoDBBackup` 新增 `restore_to_lancedb()` 方法，撈取 Mongo 有而本地 LanceDB 沒有的 chunk（含已存向量）回灌 LanceDB，**避免重新呼叫 Embedding API 產生費用與延遲**。
- **防止垃圾復活陷阱**：為了避免 Mongo 內歷史積壓的壓測孤兒/垃圾資料在 restore 時重新灌回 LanceDB，還原機制必須**排除已知的測試前綴（如 `test_*`, `qa_*` 等）**，或者**僅在 `file_id` 屬於資料庫合法登記的 store/檔案時才進行還原**。
- **呼叫時機**：在 App lifespan 啟動時，於 jti/hciot 的 backfill 執行完畢後呼叫 `restore_to_lancedb()`，補回 general（動態上傳）的資料。

### 步驟 2 — 防灌爆與孤兒主動回收（解漏洞 1）

- **API 寫入限制**：對 RAG 上傳端點加上單次/總上傳大小與筆數上限，並設置基本的速率限制。
- **孤兒回收主修法**：修改 `prune` 邏輯，不能只在 `force=True` 且只比對檔案系統 `live_files` 時才動作。必須將其升級為**主動偵測並清除前綴型孤兒（如 `test_*`）**的專屬清理機制，確保即使測試中斷或 API 寫入無實體檔案，這些孤兒也能被主動掃描並徹底清出。

### 步驟 3 — 備份資料庫參數化（解漏洞 4）

- **參數化去處**：引入環境變數 `VECTOR_BACKUP_DB`，允許管理者自訂向量備份 `vector_backup` collection 落腳的資料庫名稱，預設仍維持目前的資料庫值以確保資料不失聯。
- **避免混亂**：改名僅限於參數化備份 Collection 的存放 DB，**不對 `jti_app` 整個資料庫進行更名**，以避免動到 session、quiz 及現有正式資料而產生高昂的遷移成本。

---

## 4. 決策與設計共識 (Resolved)

1. **Restore 範圍與防線**：
   - 範圍採用「還原所有 Mongo 多出且本地 LanceDB 缺失的向量」（包括 hciot/jti 的備份），以獲得最大備份覆蓋度。
   - **安全防線**：還原時必須主動過濾並忽略測試前綴（如 `test_*`, `qa_*`），防止已刪除的垃圾資料藉由 restore 復活。
2. **壓測資料隔離與回收**：
   - 採用前綴約定（`test_*`, `qa_*`），並將 `prune` 邏輯升級為核心主動回收機制，主動比對資料庫並清除非法前綴孤兒。
3. **資料庫調整範圍**：
   - 僅將 `vector_backup` 的存放資料庫參數化為可配置，其餘 session 與正式業務資料仍留在原 DB，不做整庫改名與資料遷移。
4. **Reconcile CLI 雙向對齊指令**：
   - 開發 `scripts/reconcile_rag.py` 維護工具，用以雙向比對 LanceDB ↔ Mongo。
   - **權威性限制**：由於 LanceDB 是多部署本地儲存，從「本地 LanceDB 補回 Mongo」的寫入必須限制**只有指定的權威部署 (Authority Deployment) 才能寫入 Mongo**，其他部署僅允許進行「Mongo -> 本地 LanceDB」的單向還原同步，防止部署間向量互相覆蓋造成混亂。
