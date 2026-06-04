# JTAI RAG 啟動 Backfill 的 FD 限制與並行度優化設計

- **日期**：2026-06-05（v1 初版）
- **狀態**：Done（已實作並驗證通過）
- **分支**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **預期執行者**：Claude
- **相關文件**：[RAG 儲存完整性設計](2026-06-04-rag-storage-integrity-design.md)

---

## 1. 背景與問題描述

在實作 RAG 儲存完整性優化 v2（`general` 知識庫改為走 backfill 重建，廢除 `vector_backup` 備份還原）之後，系統在開機執行 RAG backfill 時，日誌中出現了以下錯誤：

```
[RAG] Failed to index ploom_faq_056.csv: lance error: LanceError(IO): Too many open files (os error 24)
```

該錯誤導致部分知識庫檔案無法成功被編入 LanceDB 向量資料庫，存在索引不完整或損壞的隱患。

---

## 2. 根因分析 (Root Cause)

1. **Linux 檔案描述符 (File Descriptor, FD) 限制限制**：
   Linux 對單一 Process 能同時開啟的 FD 數量設有上限。在 Docker 容器環境中，預設的限制通常為 `1024`（`ulimit -n`）。
2. **LanceDB 寫入時的 FD 消耗**：
   LanceDB 底層使用 Lance 檔案格式。在對 LanceDB 進行寫入（例如我們對單一檔案執行 `delete_by_file` 與 `insert_chunks`）時，會瞬間開啟許多檔案描述符。
3. **Lifespan 啟動時的並行寫入壓力**：
   在 `app/main.py` 的啟動流程中，原本使用 `asyncio.gather(*tasks)` 來併發執行所有知識庫來源（`jti`、`hciot` 及其多國語言版本，再加上新增的多個 `general` 知識庫）的 `run_backfill`。
   這導致多個執行緒同時對同一個 LanceDB 資料表進行大量寫入，瞬間消耗的 FD 超過 `1024` 的限制，進而觸發 `Too many open files` 錯誤。

---

## 3. 正規修復設計方案 (Solutions)

為徹底解決此隱患，我們將採取「環境設定調整」與「程式寫入控制」兩層的治本設計。

### 方案 A：提高容器內的 FD 上限（環境層）

1024 的開啟檔案限制對於資料庫類（Mongo, Elasticsearch, LanceDB 等）服務偏低。在生產/測試容器環境中，將 FD 限制提高至 65,536 是標準的配置做法。

*   **修改內容**：在 `docker-compose.yml` 的 `backend` 服務下，新增 `ulimits` 設定提升 `nofile` 軟硬限制：
    ```yaml
    backend:
      ulimits:
        nofile:
          soft: 65536
          hard: 65536
    ```

### 方案 B：序列化 (Serialize) 啟動 Backfill 寫入（程式層）

LanceDB 在同一張表上的寫入操作在底層具有鎖競爭，並行寫入無法真正提升效率，反而會急遽推高瞬間 FD 的消耗上限。因此，應控制寫入的並行度，將開機時的 backfill 改為**序列化（順序）執行**。

*   **修改內容**：修改 `app/main.py` 中的 `_run_rag_backfill`，將 `asyncio.gather` 改為簡單的迴圈與依序 `await` 呼叫。

---

## 4. 驗證與效益

1. **FD 瞬間峰值降低**：改為序列化執行後，瞬間寫入 LanceDB 的 FD 峰值將維持在極低的安全區間。
2. **容量與寫入穩定性**：即使在開機時有數十個 `general` 知識庫需要被 backfill，也不會因為 FD 限制拋出異常，確保向量資料庫索引 100% 完整。
