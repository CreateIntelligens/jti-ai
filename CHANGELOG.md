# Changelog

## [1.1.0] - 2026-06-22

通用知識庫（General）全面升級為 **per-store 多租戶架構**，新增 ESG app tier；JTI 與 ESG 遷移至共用 Managed App Runtime，後端啟動效能提升，並完善 app 隔離與安全修補。

### General — per-store 多租戶知識庫

- **per-store 知識庫**：通用知識庫（文件、圖片、topic/Q&A）全面改為以 `store_name` 為鍵的多租戶架構，各 store 資料完全隔離。
- **per-store RAG reindex**：重新索引 API 支援 per-store 粒度，同時覆蓋主知識庫與文件知識庫兩條管道。
- **per-store topics + images router**：新增通用 topics 與圖片路由，與 HCIoT category-tree 結構對齊。
- **QA knowledge workspace**：新增通用 QA 知識工作台（API client + router），掛載至 app，供前端管理。
- `store_name` 強制小寫不變性（key alignment），並補充文件說明。
- 修正：Topic 問題以扁平結構儲存以確保通用 CSV 同步正常運作。
- 安全修補：通用圖片 serving 防範 stored XSS；通用未過濾 topics listing 改為要求 admin 身份（IDOR 修補）。
- `GeneralTopicStore` 新增型別安全的 `store_name` 轉型。

### ESG App Tier

- 新增 **ESG app tier**，含統一的多應用測驗種子機制（unified multi-app quiz seeding）。
- ESG quiz 取代原色彩測驗；修正初始化 race condition 與前端按鈕尺寸。
- Quiz unique index 加入 `store_name` 防止跨 store 衝突。
- 修正：quiz bank 為空時回傳清楚的錯誤訊息。

### Managed App Runtime

- **JTI + ESG 遷移至共用 General Managed-App Runtime**：統一 session、prompt、TTS、knowledge 初始化流程。
- Chat / quiz endpoint 強制 app 隔離，並加入 lazy module loading 避免冷啟動阻塞。
- 完成 managed app runtime 功能對齊（parity），確保 JTI 與 ESG 均支援所有 runtime features。

### 效能與維運

- **RAG backfill 批次化**：backfill 階段的讀取與 fingerprint 計算改為批次操作，顯著降低啟動時的資料庫往返次數。
- **app 資料路徑整理**：`data/jti/`、`data/esg/`、`data/shared/` 路徑統一，`.gitignore` 同步更新。

### 測試

- 補齊 per-store RAG chunk 鍵值的測試驗證。
- 通用測試共用 fake mongo；backfill 文件按 source 分類撈取。
- 修正 `home_api_compat` 的 shared mongo mock，停止測試外洩。
- 更新 pytest fixture 與 JWT fixture，排除第三方套件警告（0 warnings）。

---

## [1.0.1] - 2026-06-18

### HCIoT

- **本地備份機制**：新增 HCIoT 知識庫與圖片的本地備份功能。

---

## [1.0.0] - 2026-06-09

首個正式版本。整合 JTI 活動助理、HCIoT 醫院衛教助理與通用知識庫聊天於同一後端,
具備 self-hosted RAG、三層 RBAC、DocumentDB 主庫 + Atlas 備援,以及 OpenAI-compatible API。

### 應用與 AI

- **多應用架構**:JTI、HCIoT、通用知識庫共用後端基礎設施,但各自獨立的 session manager、conversation logger、knowledge store、prompt 與 TTS。
- **Self-hosted RAG**:BAAI/bge-m3 + FlagEmbedding 產生本地 embedding,LanceDB 做向量檢索,MongoDB 做知識庫與向量備份;啟動時背景 warm up 模型並 backfill JTI/HCIoT 中英知識庫。知識庫上傳/更新/刪除會排程同步 RAG,檢索支援 `RAG_DISTANCE_THRESHOLD` 過濾。
- **OpenAI-compatible API**:`/v1/chat/completions` 先查本地 RAG 再用 Gemini 生成回答。
- **Gemini multi-key**:`GEMINI_API_KEYS` 逗號分隔多把 key,啟動掃 stores 建 key→store mapping;統一重試包裝與 grounding metadata 容錯。

### JTI

- 後端接管測驗流程,答題優先走規則(A/B/數字/選項文字),規則判不出才呼叫 LLM;測驗可中斷/重啟、支援重新生成與編輯重送(turn_number rollback)。
- 兩層 AI 架構(File Search 取來源 + Chat Session 帶 persona),session 過期可從 conversation logs 自動重建。
- 中英文測驗結果(4 種個性類型),citation 系統解析來源 image_id。
- 題庫與測驗結果支援多 bank/set、啟用切換、CSV 匯入匯出與 metadata 編輯。

### HCIoT

- 獨立 `hciot_app` 資料庫,與 JTI 完全隔離。
- 知識庫工作台:topic/category 管理、Q&A CSV 上傳(可帶 topic metadata、自動從 `q` 欄位同步題目)、多 CSV 合併預覽。
- 一般文件知識通道(非 Q&A):走 `DocumentRagService` 與獨立的 `{app}_doc_knowledge` RAG 池,不掛 topic。
- 圖片由 MongoDB image store 管理(上傳/列表/刪除/引用統計/未使用清理),前端以 `image_id` 統一引用。
- topic 預設問題可逐題隱藏(只影響前端 chips,不影響檢索);TTS 角色可在主頁選擇。

### 權限與帳號(三層 RBAC)

- 三層 role:super_admin / admin / user。一帳號綁一應用(scope),app 不進權限判斷。
- **知識庫 scope 授權**:HCIoT/JTI 的檔案、圖片、主題管理由 admin-only 改為 scope 授權 —— super_admin/admin 可跨應用,user 只能管理自己 scope 所屬應用的知識庫。
- **對話歷史**:由 admin-only 放寬給已登入 user 讀取/匯出,但 user 只能看自己應用(由綁定 store 反查 app 比對);刪除維持 admin-only。
- **對外 API key**(`sk-xxx`):Fernet 加密儲存,可在面板事後查看/複製(預設遮罩、二次確認解密);發行/更新/撤銷限 admin,user 唯讀且只看自己可見知識庫的 key。

### Session 與對話管理

- MongoDB 持久化 session 與 conversation logs:CRUD、TTL 自動清理、turn_number、rollback、分頁查詢、匯出、批次刪除與 session 重建。
- 各應用獨立資料庫(`jti_app` / `hciot_app` / `general_app`),控制面集中於 `system_config`。

### TTS

- 背景 job 產生語音並以檔案快取,支援 pending/ready/failed 狀態、TTL prune 與 job 上限。
- 中文 normalization 優先呼叫 `NORMALIZE_API_URL`,失敗或未設定時 fallback 本地 regex + OpenCC(處理 hotline、電話、年份與多位數字讀法)。

### 資料庫容錯(DocumentDB 主庫 + Atlas 備援)

- 主庫為 **AWS DocumentDB**(經 `db-tunnel` 連線),**Atlas** 作為啟動時 fallback,主庫不可用時自動頂上且資料不致大量落後。
- **DocumentDB → Atlas 同步**:平時備份,可由 super_admin 在前端按鈕(JTI/HCIoT 同步自身應用、General 全域同步含系統設定)或 cron 觸發;業務鍵 upsert、只補不刪。
- **Atlas → DocumentDB 補回**:災後恢復用,衝突以主庫(AWS)為準(只補不覆蓋);前端反向按鈕先 dry-run 預演再確認。
- 連線探測逾時放寬,避免 VPC/跳板環境冷啟動時誤判而錯誤 fallback。

### 前端

- React + Vite,JTI/HCIoT 頁面 + 通用後台;全域 i18n(中/英)、per-persona 語言隔離。
- 對話歷史(多選刪除、日期篩選、重新生成)、TTS 播放控制、知識庫工作台。

### Docker / 維運

- 單一公開 port:frontend container 內 nginx 代理 `/api`、`/v1`、`/docs`、`/health` 到 backend,其餘給 Vite。
- Backend 多階段建置(builder → runner),runtime 以非 root `appuser` 執行,entrypoint 修正 bind-mount 權限。

## [0.1.0] - 2026-04-14

### JTI — 命定前蓋測驗

- 後端完全接管測驗流程,答題判斷優先走規則(A/B/數字/選項文字),規則判不出時才呼叫 LLM
- 兩層 AI 架構:第一層 File Search(無 system_instruction,規避 flash-lite grounding bug),第二層 Chat Session(帶 persona)
- JTI agent 鎖定 gemini-2.5-flash-lite,避免較強的 model 自行進行測驗
- 測驗中途可說「中斷」暫停,隨時說「測驗」重新開始
- 支援重新生成／編輯重送(turn_number rollback),回滾後保留原有抽題序列
- Session 過期後可從 conversation logs 自動重建(`rebuild_session_from_logs`)
- 中文測驗結果:4 種個性類型(彩虹系 quiz),英文版同步支援
- Citation 系統:File Search 引用來源,附帶 image_id 解析(從 citation 檔名提取)
- 測驗問答 CSV 帶圖片的題目獨立成檔,image_id 由第一層 citation 排序決定

### HCIoT — 醫院衛教智慧助理

- 獨立的 `hciot_app` MongoDB database,與 JTI 資料完全隔離
- 知識庫管理:Topic 分類、CSV 上傳(Q&A 格式)、圖片管理(MongoDB GridFS)
- 圖片管理:上傳、更新、刪除、image picker,圖片在對話中以附件形式呈現
- Backend normalize 時自動生成 CSV index
- TTS 語音角色可透過環境變數設定

### 知識庫 / AI 基礎設施

- Gemini multi-key registry:`GEMINI_API_KEYS` 逗號分隔,啟動時掃 stores 建 key→store mapping
- `get_client_for_store(store_name)` 取對應 key,`get_default_client()` 取第一把 key
- BaseAgent 統一 File Search + Intent Check 併發邏輯,兩個 agent 共用
- `gemini_with_retry` 包裝器,所有 Gemini 呼叫統一加上重試
- File Search grounding metadata 容錯(有時為 None)
- MongoDB 知識庫檔案儲存,取代本地檔案系統

### Session / 對話管理

- `MongoSessionManager`:Session CRUD,TTL index 自動清理
- `MongoConversationLogger`:對話紀錄、turn_number、rollback、分頁查詢
- Session manager factory lazy singleton,有 MongoDB 就用,否則 fallback 記憶體版
- 修正:`get_mongo_db()` 改為必須傳入明確 db_name,預設 `"jti_app"`(修復 JTI session 落入記憶體版的 bug)
- 一般知識庫 Chat Session(`GeneralChatSessionManager`)也持久化到 MongoDB

### Frontend

- React + Vite,支援 JTI 和 HCIoT 兩個頁面
- 全域 i18n(中/英),per-persona 語言隔離
- TTS 播放控制(播放中顯示 spinner、自動重試、session 重啟自動恢復)
- 對話歷史:多選刪除、日期篩選、重新生成
- AppSelect(Radix UI)取代原生 select
- Esc 關閉所有 modal
- HCIoT workspace:Topic 分類、檔案管理、圖片 picker、CSV 格式提示、樣本下載

### TTS

- TTS job manager 改為 shared file-based cache,支援 pending/ready/failed metadata、TTL prune 與 job 上限
- JTI/HCIoT 共用中文 TTS normalization:優先呼叫 `NORMALIZE_API_URL`,失敗或未設定時 fallback 到本地 regex + OpenCC
- 中文 TTS fallback 會處理 hotline、電話、年份與三位數以上數字轉中文讀法

### Docker / Frontend / 維運

- Backend Dockerfile 採 builder -> deps -> runner 多階段建置,runtime 以非 root `appuser` 執行
- Backend entrypoint 會修正 bind-mounted `data`、`logs`、Hugging Face cache 權限,降低 Docker 權限摩擦
- Frontend container 內 nginx 維持單一公開 port,代理 `/api`、`/v1`、`/docs`、`/health` 到 backend,其他路由給 Vite
- 過濾 `/health` 與 TTS polling 202 access logs,降低開發與營運 log 噪音
- Pin `FlagEmbedding==1.3.5`,穩定 BGE-m3 embedding 依賴組合
