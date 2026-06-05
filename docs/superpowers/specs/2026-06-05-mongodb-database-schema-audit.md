# JTAI MongoDB 資料庫集合審計與命名規範化規劃書

- **日期**：2026-06-05（v1 初版；同日 v2 以 MongoDB MCP 直連 Atlas 實測校正審計表，並補充程式碼落點）
- **狀態**：Draft（規劃與待辦稽核清單）
- **相關文件**：[App↔Store 層級與授權](2026-06-02-app-store-hierarchy-and-scope.md)、[啟動 Backfill 的 FD 限制與並行度優化](2026-06-05-rag-backfill-fd-leak-resolution.md)

---

## 1. 背景與動機

在進行 RAG 儲存完整性重構時，排查發現 MongoDB 中積壓了許多歷史遺留、用途不明、或「命名/歸屬不一致」的資料庫集合（Collections）。為維護系統架構的整潔度與未來多租戶（Multi-tenancy）遷移的便利性，特撰寫此文件記錄當前審計結果，並規劃未來的「資料庫清掃與命名規範化」任務。

---

## 2. 當前資料庫集合審計 (Current Audit)

> **v2 修訂（2026-06-05，以 MongoDB MCP 直連 Atlas `poc0` cluster 實測校正）**
> v1 初版把所有集合當成都寄居在單一 `jti_app` 庫，且對數個集合的歸屬與處置判斷有重大錯誤。實測後發現實際是**三個獨立 database**，且其中被 v1 標為「可安全刪除」的那個庫，其實是**活的控制面庫（Control Plane）**，存放全系統登入帳號。
>
> **命名說明**：該控制面庫目前在 Atlas 中的實體名稱仍是早期遺留的 `gemini_notebook`，但其角色早已是全系統控制面。本文件後續一律以**「控制面庫」**稱呼它（實體名 `gemini_notebook`、規劃改名 `system_config`），以反映真實職責、避免被舊名誤導。以下為校正後的真實結構。

### 2.0 實際資料庫拓樸（三庫）

實測（`list-databases` / `list-collections` / `count`）結果，系統資料分布於三個獨立 database（另有 MongoDB 內建的 `admin`、`local` 系統庫，size 0，不可動）：

| Database | 角色 | 集合（文件數） |
| :--- | :--- | :--- |
| **控制面庫**（實體名 `gemini_notebook`） | ⚠️ **控制面（活的基礎設施庫）** | `users`(4)、`prompts`(15)、`api_keys`(2)、`sessions`(0)、`conversations`(0) |
| **`jti_app`** | JTI 數據面 | `sessions`、`conversations`、`knowledge_stores`(2)、`knowledge_files`(212)、`quiz_results`(9)、`quiz_results_metadata`、`quiz_bank_questions`(36)、`quiz_bank_metadata`、`vector_backup`(1) |
| **`hciot_app`** | HCIoT 數據面 | `sessions`、`conversations`、`knowledge_files`(153)、`hciot_topics`、`hciot_categories`、`hciot_images` |
| **`general_app`** | General 數據面（**v2 新建**） | `sessions`(1,241)、`conversations`(357) — 由 jti_app 遷出，見 §2.4 |

> **v2 更新**：原本 general（動態知識庫，如 fish 等店）的 session / conversation **寄生在 `jti_app`**，與 JTI 測驗 session 混在同一集合。已拆出獨立的 **`general_app`** 庫並完成資料遷移（見 §2.4）。`jti_app` 上的數字會因此次清理 + 遷移而下降。

> 🔴 **最關鍵修正**：控制面庫（v2 審計時實體名為 `gemini_notebook`）**不是** Playground 殘留，更**不可刪除**。其 `users` 集合存著全系統登入帳號（1 個 super_admin + 3 個 user，帳號名從略）。它本質上就是 §3 的「控制面 / `system_config`」。
>
> ✅ **已處置（2026-06-05）**：已正名遷移為 `system_config` 並 drop 舊庫（見 §2.5）。上方拓樸表的「控制面庫」現對應實體 `system_config`，三 manager（`users.py`/`prompts.py`/`api_keys.py`）改引用集中常數 `CONTROL_PLANE_DB_NAME`。

### 2.1（原 §2 表）逐集合校正與處置

| 集合（所屬 DB） | 實測狀態 | 用途說明 | 校正後處置 |
| :--- | :--- | :--- | :--- |
| **`users`**（`gemini_notebook`） | 4 筆 | 全系統後台登入帳號、密碼雜湊與角色權限。 | **保留**；未來隨控制面遷移（改名 `system_config`）。 |
| **`prompts`**（`gemini_notebook`） | 15 筆 | 後台提示詞模版切換與設定。 | **保留**（v1 誤植在 `jti_app`，實際在控制面庫）。 |
| **`api_keys`**（`gemini_notebook`） | 2 筆 | 金鑰管理。v1 標「待確認/jti_app」，**實際在控制面庫且為活資料**。 | **保留**；隨控制面遷移。 |
| **`sessions`**（`jti_app` / `hciot_app`） | 33,989 / 17,780 | JTI / HCIoT 進行中即時狀態。 | **保留**；嚴重積壓，見 §2.2 與 §2.3。 |
| **`conversations`**（`jti_app` / `hciot_app`） | 3,460 / 4,405 | 對話歷史訊息。 | **保留**。 |
| **`knowledge_stores`**（`jti_app`） | 2 筆 | 通用/動態知識庫中央註冊表。 | **保留**；未來遷移至控制面庫。 |
| **`knowledge_files`**（`jti_app` / `hciot_app`） | 212 / 153 | 知識庫上傳的原始檔案。 | **保留**。 |
| **`quiz_results` / `_metadata`**（`jti_app`） | 9 / — | JTI 計分規則與色塊分析模版、版本元數據。 | **保留**。 |
| **`quiz_bank_questions` / `_metadata`**（`jti_app`） | 36 / — | JTI 題目內容與題庫元數據。 | **保留**。 |
| **`hciot_topics` / `_categories` / `_images`**（`hciot_app`） | 有資料 | HCIoT 衛教主題、分類、圖片。v1 完全未列。 | **保留**。 |
| **`vector_backup`**（`jti_app`） | 1 筆（內容空） | RAG 完整性重構的備份產物。v1 完全未列。 | 🔍 待確認用途後決定保留/清理。 |
| ~~`general_chat_sessions`~~ | **不存在** | v1 列為待 drop 的舊集合。 | ✅ 兩庫均查無此集合，**已不存在**，checklist 對應動作無對象。 |
| ~~`quizzes`~~ | **不存在** | v1 列為待 drop 的廢棄集合。 | ✅ 同上，**已不存在**。 |
| ~~`admin`（當成 jti_app 集合）~~ | 誤判 | v1 當成早期後台設定集合。 | ❌ 實為 MongoDB 內建系統庫（database），**不可動**。 |
| ~~`gemini_notebook`（當成可刪集合）~~ | 嚴重誤判 | v1 標「預計可安全刪除」。 | 🔴 實為控制面 database，見 §2.0，**絕對不可刪**。 |

---

### 2.2 Sessions 集合空對話資料積壓專題分析

#### 現象描述（實測校正）
`sessions` 集合積壓了極多 `step: "WELCOME"`、答案為空 `{}`、對話紀錄為空 `[]` 的文件，部分可追溯至數個月前。實測量化結果比 v1 描述更嚴重：

| DB | sessions 總數 | `step=WELCOME` | 佔比 |
| :--- | ---: | ---: | ---: |
| `jti_app` | 33,989 | 33,438 | **98%** |
| `hciot_app` | 17,780 | （同模式） | — |

合計約 **5.2 萬筆** 待清理 session。

#### 根因分析（已對照程式碼確認）
1. **網頁載入即落庫 Session**：
   前端組件掛載時呼叫 `/chat/start`（jti/hciot）或 `/start`（general）取開場歡迎語。後端在此**立即將一筆 `WELCOME` session upsert 寫入 MongoDB**。而歡迎語 jti/hciot 其實是靜態常數 `_OPENING_MESSAGE`，**根本不依賴 session**——session 是被白白生出來的。使用者路過、重整都會殘留一筆。詳細落點見 §2.3。
2. **TTL 自動清理機制被關閉（為了測驗續答功能）**：
   系統最初在 `app/services/mongo_client.py` 設有 TTL 過期索引（`expires_at`）。但在 2026-02-13 Commit `8928908` 中，為支援 **「測驗中斷續答 (Quiz Resume)」**（讓使用者隔天仍能接著答題），移除了該 TTL 索引。**實測確認**：當前 `Session` 模型（`app/models/session.py`）已無 `expires_at` 欄位，且 `mongo_session_manager.py:284` 在 rebuild 時還會主動剝除殘留的 `expires_at`，導致所有歷史 session 永久保留。

---

### 2.3 程式碼現況與 A/B 實作落點（2026-06-05 確認）

> 本節記錄對照原始碼後的事實，以及兩個解法（A 治本、B 兜底）的具體落點。**截至撰寫時尚未動任何程式碼**。

#### 2.3.1 三 app 的 session 落庫路徑（皆會立即落庫）

| 入口 | 落庫行為 | 檔案:行 |
| :--- | :--- | :--- |
| **jti** `POST /chat/start` | `create_session` 立即 `upsert` | `app/routers/jti/chat.py:98` → `app/services/session/mongo_session_manager.py:164` |
| **hciot** `POST /chat/start` | 同上（共用同一 `MongoSessionManager`） | `app/routers/hciot/chat.py:91` → 同 `:164` |
| **general** `POST /start` | `create_session` upsert **後再 `update_session` 寫 metadata（兩次寫）** | `app/services/general/main_agent.py:193` + `:202` |

#### 2.3.2 已成立的前提（讓 A 可行）

- ✅ **單 worker**：compose 啟動為 `uvicorn app.main:app ... --reload`，無 `--workers`（`--reload` 本身亦僅單 worker）。→ `_pending` 純記憶體 lazy 安全，無跨 worker 漏讀問題。
- ✅ **`get_session` 已先查 `_pending`**（`mongo_session_manager.py:173`）→ lazy 化後，第一則訊息打 `/chat/message` 仍讀得到尚未落庫的 session。
- ⚠️ **`_pending` 現況不是 lazy-write，而是「DB 寫失敗的 fallback」**（`:167` 在 `except` 才寫入）。要做 A 需反轉其語意。

#### 2.3.3 方案 A — Lazy 建 session（治本，從源頭擋住新增）

- **核心**：改 `MongoSessionManager.create_session`，預設**只放 `_pending`、不寫 DB**。
- **Flush 時機**：第一則真實使用者訊息進來時才落庫。`update_session` 成功後已會 `pop _pending`（`:192`），可作為 flush 點。
- **general 額外處理** ⚠️：`main_agent.py:202` 的 metadata `update_session` 會立即把 session flush 落庫，違反 lazy。需改為將 metadata 寫進 `_pending` 中的物件、不立即 `update_session`。
- jti/hciot 的 router 不需改（改底層 manager 即自動生效）。

#### 2.3.4 方案 B — 動態 TTL（兜底，清理新舊積壓 + 補強重整殘留）

- `app/models/session.py`：新增 `expires_at` 欄位。
- 寫入時依 `step` 計算過期：`WELCOME` / `DONE` 短（例如 1 天）；`QUIZ` 長（例如 7 天，保障續答）。
- `app/services/mongo_client.py` 的 `_ensure_base_indexes`：加 `sessions.create_index("expires_at", expireAfterSeconds=0)`，**三庫（`jti_app` / `hciot_app` / `gemini_notebook`）都要建**。
- 移除 `mongo_session_manager.py:284` 對 `expires_at` 的剝除邏輯。

#### 2.3.5 建議組合

**A 為主、B 為輔**：A 從源頭杜絕新的空 session；B 兜底清理既有 5.2 萬筆積壓，並涵蓋少數 A 漏網的情境（如 start 後重整未對話）。歷史積壓的一次性清理腳本另行處理（見 §4 checklist，使用者指示「晚點再清」）。

> **狀態（2026-06-05）**：A + B 已實作並套用至執行中後端，TTL 索引（`expireAfterSeconds=0`）於 `jti_app` / `hciot_app` / `general_app` 三庫的 `sessions` 集合皆已建立。WELCOME/DONE 3 天、QUIZ/SCORING/RECOMMEND 7 天。歷史 40,992 筆空 session（jti_app 31,201 + hciot_app 9,791）已清理完成。

---

### 2.4 General 數據面拆庫：general_app（2026-06-05 完成）

#### 問題
general（動態知識庫，如 fish 等店）的 session 與 conversation 過去**寄生在 `jti_app`**：
- session manager 與 conversation logger 都指向 `jti_app`（`session_manager_factory.py`、`routers/general/chat.py`）
- 後果：general 對話狀態與 JTI 測驗 session 混在同一個 `jti_app.sessions` / `jti_app.conversations` 集合，違反「數據面各 app 獨立庫」原則。

#### 處置（已完成）
1. **DB 名常數集中化**：新增 `app/services/db_names.py`，統一定義 `JTI_DB_NAME` / `HCIOT_DB_NAME` / `GENERAL_DB_NAME` / `CONTROL_PLANE_DB_NAME`，取代散落各處的字面字串。
2. **general 改指 `general_app`**：
   - `get_general_chat_session_manager()` → `MongoSessionManager(db_name=GENERAL_DB_NAME)`
   - 新增 `get_general_conversation_logger()` → `MongoConversationLogger(db_name=GENERAL_DB_NAME)`，取代原本借用的 `get_jti_conversation_logger()`
   - 於 `deps.py` 啟動 warmup 一併初始化（建立 `general_app` 索引含 TTL）。
3. **資料遷移**：`scripts/migrate_general_to_general_app.py`，判別規則
   - sessions：`metadata.store_name` 存在 → general
   - conversations：`mode == "general"` → general
   流程為 copy → 驗證筆數 → 刪除來源（冪等、可 `--dry-run` / `--no-delete`）。

#### 結果（實測）
- 遷移 **1,241 sessions + 357 conversations** → `general_app`，來源 `jti_app` 對應資料歸零。
- `general_app.sessions` 取得完整索引含 TTL；end-to-end 驗證 general 走 lazy 建立、首則訊息落 `general_app` 並帶 `expires_at`。

#### 仍保留在 jti_app（刻意不搬）
- `knowledge_stores` / `knowledge_files`：是**跨 app 的共用註冊表**（以 `managed_app` 區分 jti/hciot/general），屬控制面範疇，規劃隨控制面遷移（見 §3），不併入 general_app。
- 另發現 13 筆 `metadata.app_mode=hciot` 卻殘留在 `jti_app.sessions` 的錯庫資料，不在本次範圍，留待後續核對。

---

### 2.5 控制面庫改名：gemini_notebook → system_config（2026-06-05 完成）

#### 問題
控制面三件（`users` 登入帳號、`prompts` 提示詞、`api_keys` 金鑰）原本落在早期遺留名 `gemini_notebook`，語意誤導（曾被 v1 誤判為可刪 Playground 殘留）。

#### 處置（已完成）
MongoDB 無 rename database，採「複製 → 切程式碼 → 驗證 → 刪舊庫」：
1. **集中常數**：`db_names.py` 的 `CONTROL_PLANE_DB_NAME` 由 `gemini_notebook` 改為 `system_config`；`app/users.py`、`app/prompts.py`、`app/api_keys.py` 的 `DB_NAME` 改引用此常數（不再 hardcode）。舊腳本 `scripts/migrate_prompt_index.py` 一併更新。
2. **資料複製**：`scripts/migrate_control_plane_to_system_config.py`，以自然鍵 upsert（users→username、prompts→store_name、api_keys→key_hash），含 `--dry-run` / `--drop-source` 安全閘（目的庫筆數 < 來源則拒刪）。
3. **空殼丟棄**：`gemini_notebook` 的 `sessions` / `conversations`（皆 0 筆，從未使用）隨舊庫一併刪除，不遷移。

#### 結果（實測）
- 複製 **users(4) + prompts(15) + api_keys(2)** → `system_config`，三 manager 啟動皆連到 `system_config`。
- 登入路徑驗證:`UserManager.get_by_username` 讀回 super_admin 帳號正常；auth/security/session 測試綠（93 passed，唯一 fail 為既有 `test_passwords` 與本變更無關）。
- 舊庫 `gemini_notebook` 已 drop；Atlas 現有庫:`system_config` / `jti_app` / `hciot_app` / `general_app`（+ 內建 `admin`/`local`）。

#### 你的提問釐清
- **「gemini_notebook 裡的 general 資料要搬嗎?」** → 沒有。其 `sessions`/`conversations` 是 0 筆空殼，general 對話一直在 jti_app（已搬 general_app）。已隨舊庫刪除。
- **「帳號管理 / key 的位置?」** → 位置本來就對（獨立於各 app 庫），問題只在名字；已正名為 `system_config`。
- **「釋放 admin?」** → 若指**帳號/RBAC 權限層**（super_admin 收斂等），那是另一條線，屬 auth-rbac 設計範疇，不在本次 DB 結構調整內，留待 RBAC 文件處理。

---

### 2.6 knowledge_stores 遷入控制面 + hciot 錯庫資料歸位（2026-06-05 完成）

#### knowledge_stores → system_config
- **判別**：`knowledge_stores` 是跨 app 的中央知識庫註冊表（以 `managed_app` 區分 jti/hciot/general），且僅 `StoreRegistry`（`routers/general/stores.py`）一處讀寫 → 屬控制面，低風險。
- **處置**：`StoreRegistry.__init__` 預設 db 由 `jti_app` 改為 `CONTROL_PLANE_DB_NAME`；複製 2 筆 → `system_config`，切程式碼驗證（`StoreRegistry` 連到 system_config）後 drop `jti_app.knowledge_stores`。
- **`knowledge_files` 不遷**：經查它是各 app 自己上傳的檔案（數據面），非共用註冊表——`jti_app.knowledge_files`(212，jti+general 以 namespace 共用)、`hciot_app.knowledge_files`(153) 各自獨立，留在數據面。

#### hciot 錯庫資料歸位
- 發現 `jti_app` 殘留 hciot 的真實歷史:**13 sessions**（`metadata.app_mode=hciot`，皆有對話、最新 2026-03-04）+ **22 conversations**（`mode=hciot`）。
- 因有對話內容（非空殼），處置為**遷回 `hciot_app`**（非刪除）：確認無 session_id 衝突 → copy → 驗證 → 刪 `jti_app` 來源。`jti_app` 現已無任何 hciot 殘留。

---

### 2.7 general 對話的知識庫歸屬：conversations 補 store_name（2026-06-05 完成）

#### 問題
`general_app` 是單一庫、多個動態店（fish 類，及走 general 介面選 managed store 的 `__jti__`/`__hciot__`）共用 `sessions` / `conversations` 集合。
- `sessions` 已有 `metadata.store_name` 可分辨店；
- 但 **`conversations` 只有 `mode="general"`，沒有 store 標記** → 查「某店的對話歷史」必須反查 session，且 session 被 TTL 清掉後就無從得知。

#### 處置（已完成）
1. **寫入補欄位**：`MongoConversationLogger.log_conversation` 新增 `store_name` 參數，落為**頂層可查欄位**；general 路由 (`routers/general/chat.py`) 從 `session.metadata.store_name` 帶入。jti/hciot 不傳，向後相容。
2. **索引**：`_ensure_conversation_indexes` 加 `store_name` **sparse 索引**（jti/hciot 無此欄位不佔空間）。
3. **回填**：對既有 general_app conversations 由其 session 的 `metadata.store_name` 回填。

#### 結果（實測）
- 新對話即時帶 `store_name`（端到端驗證通過）。
- 回填：126 筆成功；**231 筆為孤兒**（對應 session 已被先前 TTL/空-session 清理刪除，store 資訊不可復原）。
- 孤兒處置：經確認 231 筆全為「store_name 缺失 **且** session 已不存在」（0 筆誤判），已刪除。`general_app.conversations` 現存 127 筆，**100% 帶 store_name**，皆可歸屬到店。

---

## 3. 未來規劃：中央管理面與數據面分離 (Target Architecture)

為了徹底解決全域管理資料寄居在特定應用資料庫的問題，資料庫架構依以下規範優化（控制面與 general 拆庫已於 2026-06-05 落地）：

1.  **控制面 (Control Plane) - 全域資料庫 `system_config`**：
    *   負責跨租戶、跨應用的全系統管理。
    *   包含：`users`（全域帳號）、`api_keys`（金鑰管理）、`prompts`（提示詞模版）、`knowledge_stores`（中央知識庫註冊表）。
    *   ✅ **已完成正名**：由 `gemini_notebook` 遷移改名為 `system_config`（見 §2.5）。
    *   ✅ **`knowledge_stores` 已遷入**（見 §2.6）：跨 app 註冊表自 `jti_app` 移至 `system_config`。
    *   ⚠️ **`knowledge_files` 刻意不遷**：它是**各 app 自己上傳的檔案（數據面）**，不是共用註冊表——`jti_app.knowledge_files`（jti + general 以 namespace 共用）、`hciot_app.knowledge_files` 各自獨立，應留在數據面。
2.  **數據面 (Data Plane) - 各應用專屬資料庫 (`jti_app`, `hciot_app`, `general_app`)**：
    *   各應用獨立且隔離，不跨庫讀取。
    *   `jti_app` 僅保留 JTI 特有的：`sessions`、`conversations`、`quiz_*` 模版等。
    *   `hciot_app` 僅保留 HCIoT 的：`sessions`、`conversations`、`hciot_*`。
    *   ✅ **`general_app` 已建立並完成遷移**（見 §2.4）：general 的 `sessions`、`conversations` 已從 `jti_app` 拆出。

---

## 4. 後續待辦與命名規範化核對清單 (Audit Checklist)

在下一階段重構或系統清掃時，應依此核對清單進行操作：

**A. Session 積壓（v2 重點，見 §2.3）**
- [x] **方案 A（lazy 建 session）**：`create_session` 預設只進 `_pending`；首則真實訊息才 flush 落庫；jti/hciot/general 三處「開頁即落庫」皆已移除。
- [x] **方案 B（動態 TTL）**：`compute_expires_at` 依 `step` 算過期（WELCOME/DONE 3 天、QUIZ 系列 7 天）；三庫建 `expireAfterSeconds=0` TTL 索引。
- [x] **歷史一次性清理**：已刪除 `jti_app` 31,201 + `hciot_app` 9,791 = 40,992 筆空 session（30 天前、無對話、WELCOME/DONE）。

**A2. General 拆庫（v2，見 §2.4）**
- [x] 新增 `app/services/db_names.py` 集中 DB 名常數。
- [x] general session manager + conversation logger 改指 `general_app`。
- [x] 遷移 1,241 sessions + 357 conversations 至 `general_app`，jti_app 對應資料歸零。

**B. 控制面正名（v2，見 §2.5）**
- [x] `db_names.py` 集中 `CONTROL_PLANE_DB_NAME`；`users.py`/`prompts.py`/`api_keys.py` 改引用常數。
- [x] 複製 users(4)+prompts(15)+api_keys(2) 至 `system_config`，切程式碼、驗證登入。
- [x] drop 舊庫 `gemini_notebook`（含 0 筆空殼 sessions/conversations）。

**C. 集合清理 / 錯庫歸位（v2 校正：原 v1 多數對象不存在或誤判）**
- [x] ~~drop `general_chat_sessions` / `quizzes`~~ → **已不存在，無需動作**（v2 實測確認）。
- [x] 13 sessions + 22 conversations 的 hciot 錯庫資料（含對話）已遷回 `hciot_app`，jti_app 歸零（見 §2.6）。
- [x] `jti_app.vector_backup`（1 筆測試殘留向量，`source_type=hciot_knowledge`、text 為測試亂打內容）已確認非業務資料，drop。

**D. 命名統一化 (Naming Convention)**
- [x] 即時對話狀態各庫統一 **`sessions`**（jti/hciot/general 皆是）。
- [x] 對話歷史統一 **`conversations`**。
- [x] 題庫與測驗模版統一 `quiz_` 前綴（quiz_results/quiz_results_metadata/quiz_bank_questions/quiz_bank_metadata 皆符合）。

**F. general store_name 落欄位 + 查詢（見 §2.7）**
- [x] conversations 寫入 `store_name` 頂層欄位 + sparse 索引；回填既有資料（126 成功、231 孤兒）。
- [x] general 歷史查詢改以 `store_name` OR `session_snapshot.store` 比對（新資料走索引、舊資料相容）。

**E. 控制面遷移（見 §3）**
- [x] `knowledge_stores`（跨 app 註冊表）由 `jti_app` 遷入 `system_config`（見 §2.6）。
- [N/A] `knowledge_files` **不遷**：各 app 自己的檔案屬數據面，留在 `jti_app` / `hciot_app`。
