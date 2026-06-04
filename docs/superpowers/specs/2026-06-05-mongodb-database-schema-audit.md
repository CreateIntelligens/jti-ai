# JTAI MongoDB 資料庫集合審計與命名規範化規劃書

- **日期**：2026-06-05（v1 初版，補充 Session 積壓專題）
- **狀態**：Draft（規劃與待辦稽核清單）
- **相關文件**：[App↔Store 層級與授權](2026-06-02-app-store-hierarchy-and-scope.md)、[啟動 Backfill 的 FD 限制與並行度優化](2026-06-05-rag-backfill-fd-leak-resolution.md)

---

## 1. 背景與動機

在進行 RAG 儲存完整性重構時，排查發現 MongoDB 中積壓了許多歷史遺留、用途不明、或「命名/歸屬不一致」的資料庫集合（Collections）。為維護系統架構的整潔度與未來多租戶（Multi-tenancy）遷移的便利性，特撰寫此文件記錄當前審計結果，並規劃未來的「資料庫清掃與命名規範化」任務。

---

## 2. 當前資料庫集合審計 (Current Audit)

以下為目前在 `jti_app` 等資料庫中偵測到的集合清單、其當前用途分析，以及後續建議：

| 集合名稱 (Collection) | 目前狀態/內容 | 所屬模組 | 用途說明 | 建議處置方案 |
| :--- | :--- | :--- | :--- | :--- |
| **`users`** | 有資料 | 權限 (RBAC) | 儲存全系統後台登入帳號、密碼雜湊與角色權限。 | **保留**，但未來應遷移至全域管理庫。 |
| **`sessions`** | 有資料 | 狀態機 (JTI/HCIoT) | 儲存 JTI / HCIoT 進行中的即時狀態（問答進度、答案快取）。 | **保留**（詳細分析見下文 2.1）。 |
| **`conversations`** | 有資料 | 對話歷史 | 儲存使用者與 AI 對話的完整歷史訊息（用於後台檢視及歷史清單）。 | **保留**。 |
| **`prompts`** | 有資料 | 提示詞管理 | 儲存後台提示詞模版切換與設定的紀錄。 | **保留**。 |
| **`knowledge_stores`** | 有資料 | 知識庫 (General) | 通用與動態知識庫的中央註冊表。 | **保留**，未來應遷移至全域管理庫。 |
| **`knowledge_files`** | 有資料 | 知識庫 (General) | 儲存動態/通用知識庫上傳的原始檔案。 | **保留**。 |
| **`quiz_results`** | 有資料 | JTI 測驗 | 儲存 JTI 人格測驗的計分規則與色塊分析內容模版。 | **保留**。 |
| **`quiz_results_metadata`** | 有資料 | JTI 測驗 | 儲存 JTI 測驗結果的版本與元數據。 | **保留**。 |
| **`quiz_bank_questions`** | 有資料 | JTI 測驗 | 儲存 JTI 測驗題目內容數據。 | **保留**。 |
| **`quiz_bank_metadata`** | 有資料 | JTI 測驗 | 儲存 JTI 測驗題庫的元數據。 | **保留**。 |
| **`general_chat_sessions`**| 空或舊資料 | 一般知識庫對話 | 重構前使用的舊對話 Session 集合。目前代碼已刪除其讀寫邏輯。 | ⚠️ **可安全刪除 (Drop)**。 |
| **`quizzes`** | 空的 | JTI 測驗 | 最初設計用以單獨存放完成測驗的歷史，後已廢棄不用。 | ⚠️ **可安全刪除 (Drop)**。 |
| **`api_keys`** | 待確認 | 金鑰管理 | 過去可能用於儲存使用者自帶 Gemini 金鑰的歷史或設定。 | 🔍 **待核對確認後清理**。 |
| **`admin`** | 待確認 | 系統管理 | 早期後台管理的基礎設定檔。 | 🔍 **待核對確認後清理**。 |
| **`gemini_notebook`** | 待確認 | 早期功能 | 過去可能用於 Notebook 實驗室或 Playground 階段的殘留。 | ⚠️ **預計可安全刪除**。 |

---

### 2.1 Sessions 集合空對話資料積壓專題分析

#### 現象描述
在實際環境中，`sessions` 集合積壓了極多 `step: "WELCOME"`、答題答案為空 `{}`、且對話紀錄為空 `[]` 的文件，有些甚至可追溯至數個月前（如 3 月份），顯示自動清理機制並未生效。

#### 根因分析
1. **網頁載入即初始化 Session**：
   在 JTI、HCIoT 與 General 前端組件掛載時（`useEffect` 階段），為了向後端獲取開場歡迎語（Opening Message）以呈現給使用者，前端會自動呼叫對話啟動介面。這會在資料庫中立即新增一筆 `WELCOME` 狀態的 Session。若使用者僅是路過開啟頁面、或頻繁重新整理網頁，便會殘留大量無效的空 Session。
2. **TTL 自動清理機制被關閉（為了測驗續答功能）**：
   系統最初在 `app/services/mongo_client.py` 設有 TTL 自動過期索引（`expires_at`）。
   但在 2026 年 2 月 13 日的 Commit `8928908` 中，為了修復與支援 **「測驗中斷續答 (Quiz Resume)」** 功能（讓使用者即使隔天回來也能接著答題），開發團隊移除了該 TTL 索引。由於當前 `Session` 模型不再寫入 `expires_at` 欄位，這導致所有歷史 Session 文件均被永久保留，造成嚴重的資料積壓。

#### 建議優化方案
*   **短期處置**：定期手動執行清理指令，刪除建立時間超過 30 天且步驟依然處於 `WELCOME` 或 `DONE` 狀態的無效 Session。
*   **長期改進（動態 TTL 機制）**：
    *   重新啟用 MongoDB 的 TTL 索引 `sessions.create_index("expires_at", expireAfterSeconds=0)`。
    *   在 `Session` 模型與 `MongoSessionManager` 寫入時，引入動態 `expires_at` 計算：
        *   若 `step` 處於 `WELCOME`（剛打開網頁未對話）或 `DONE`（已測驗完成），設定較短的過期時間（例如 1 天）。
        *   若 `step` 處於 `QUIZ` 答題中狀態，設定較長的過期時間（例如 7 天），確保使用者在答題中斷後仍有足夠的時間回來續答。

---

## 3. 未來規劃：中央管理面與數據面分離 (Target Architecture)

為了徹底解決全域管理資料（如 `knowledge_stores`）寄居在特定應用資料庫（如 `jti_app`）的問題，未來的資料庫架構應依據以下規範進行優化：

1.  **控制面 (Control Plane) - 全域資料庫 `system_config`**：
    *   負責跨租戶、跨應用的全系統管理。
    *   包含：`users`（全域帳號）、`knowledge_stores`（中央知識庫註冊表）、`api_keys`（金鑰管理）。
2.  **數據面 (Data Plane) - 各應用專屬資料庫 (e.g. `jti_app`, `hciot_app`, `general_app`)**：
    *   各應用獨立且隔離，不跨庫讀取。
    *   `jti_app` 僅保留 JTI 特有的：`sessions`、`conversations`、`quizzes` 模版等。
    *   `hciot_app` 僅保留 HCIoT 的：`sessions`、`conversations`。

---

## 4. 後續待辦與命名規範化核對清單 (Audit Checklist)

在下一階段重構或系統清掃時，應依此核對清單進行操作：

- [ ] **歷史集合清理**：在開發/生產環境的安全備份下，手動 `drop` 掉 `general_chat_sessions` 與 `quizzes`。
- [ ] **代碼殘留核對**：確認代碼中（特別是舊測試或腳本）是否還有寫死引用這些被刪除集合的邏輯。
- [ ] **命名統一化 (Naming Convention)**：
  *   所有即時對話流程狀態，統一命名為 **`sessions`**（例如各庫都用這個名字，不用 `xxx_sessions`）。
  *   所有對話歷史訊息，統一命名為 **`conversations`**。
  *   所有題庫與測驗模版，統一使用 `quiz_` 前綴（如 `quiz_bank_questions`）。
- [ ] **獨立管理資料庫規劃**：規劃 `system_config`（或 `jti_system`）連線，將 `users` 和 `knowledge_stores` 順利遷移。
