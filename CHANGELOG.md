# Changelog

## [Unreleased] - 2026-04-29

### RAG / AI 基礎設施

- Self-hosted RAG 成為主要檢索路徑：BAAI/bge-m3 + FlagEmbedding 產生 embedding，LanceDB 做本地向量檢索，MongoDB 做知識庫與向量備份
- FastAPI lifespan 會背景 warm up embedding model，並自動 backfill JTI/HCIoT 的中英文知識庫
- 知識庫上傳、更新、刪除後會排程同步 RAG；CSV 以 row 為 chunk，並保留 `img` 欄位解析出的 `image_id`
- `/v1/chat/completions` 改為 OpenAI-compatible 入口，會先查本地 RAG，再用 Gemini 產生回答
- RAG 檢索新增 distance threshold，可用 `RAG_DISTANCE_THRESHOLD` 調整結果過濾

### 應用切分與後端整理

- JTI、HCIoT 的 service wiring 已拆開：各自擁有 session manager、conversation logger、knowledge store 與 TTS manager
- 共用 persona router factory、safety prompts、緊急電話讀法與知識庫工具，減少跨 app 分支邏輯
- MongoDB session/conversation storage 測試補強，包含 rollback、session rebuild、分頁與匯出流程

### HCIoT 工作台

- HCIoT 知識庫工作台支援 topic/category 管理，CSV 上傳可帶 topic metadata，並自動從 `q` 欄位同步題目
- 新增 topic 合併 CSV API 與前端整合預覽，支援同 topic 多個 CSV 合併檢視與編輯
- 圖片改由 MongoDB image store 管理，支援上傳、列表、刪除、引用次數統計與未使用圖片清理
- 圖片引用統一使用 `image_id`，前端以 `normalizeImageId()` 和 `/api/hciot/images/{image_id}` 載入
- HCIoT TTS 角色選擇移到主要頁面，送出訊息時可指定 voice

### JTI

- JTI 回應組裝、測驗流程、quiz bank/result store 與 TTS 文本產生已模組化
- 題庫與測驗結果管理支援多 bank/set、啟用切換、CSV 匯入匯出與 metadata 編輯
- 知識庫上傳/編輯會拒絕 `[CORE: ...]` 標記，避免把內部優先權語法寫入可檢索內容

### TTS

- TTS job manager 改為 shared file-based cache，支援 pending/ready/failed metadata、TTL prune 與 job 上限
- JTI/HCIoT 共用中文 TTS normalization：優先呼叫 `NORMALIZE_API_URL`，失敗或未設定時 fallback 到本地 regex + OpenCC
- 中文 TTS fallback 會處理 hotline、電話、年份與三位數以上數字轉中文讀法

### Docker / Frontend / 維運

- Backend Dockerfile 採 builder -> deps -> runner 多階段建置，runtime 以非 root `appuser` 執行
- Backend entrypoint 會修正 bind-mounted `data`、`logs`、Hugging Face cache 權限，降低 Docker 權限摩擦
- Frontend container 內 nginx 維持單一公開 port，代理 `/api`、`/v1`、`/docs`、`/health` 到 backend，其他路由給 Vite
- 過濾 `/health` 與 TTS polling 202 access logs，降低開發與營運 log 噪音
- Pin `FlagEmbedding==1.3.5`，穩定 BGE-m3 embedding 依賴組合

## [0.1.0] - 2026-04-14

### JTI — 命定前蓋測驗

- 後端完全接管測驗流程，答題判斷優先走規則（A/B/數字/選項文字），規則判不出時才呼叫 LLM
- 兩層 AI 架構：第一層 File Search（無 system_instruction，規避 flash-lite grounding bug），第二層 Chat Session（帶 persona）
- JTI agent 鎖定 gemini-2.5-flash-lite，避免較強的 model 自行進行測驗
- 測驗中途可說「中斷」暫停，隨時說「測驗」重新開始
- 支援重新生成／編輯重送（turn_number rollback），回滾後保留原有抽題序列
- Session 過期後可從 conversation logs 自動重建（`rebuild_session_from_logs`）
- 中文測驗結果：4 種個性類型（彩虹系 quiz），英文版同步支援
- Citation 系統：File Search 引用來源，附帶 image_id 解析（從 citation 檔名提取）
- 測驗問答 CSV 帶圖片的題目獨立成檔，image_id 由第一層 citation 排序決定

### HCIoT — 醫院衛教智慧助理

- 獨立的 `hciot_app` MongoDB database，與 JTI 資料完全隔離
- 知識庫管理：Topic 分類、CSV 上傳（Q&A 格式）、圖片管理（MongoDB GridFS）
- 圖片管理：上傳、更新、刪除、image picker，圖片在對話中以附件形式呈現
- Backend normalize 時自動生成 CSV index
- TTS 語音角色可透過環境變數設定

### 知識庫 / AI 基礎設施

- Gemini multi-key registry：`GEMINI_API_KEYS` 逗號分隔，啟動時掃 stores 建 key→store mapping
- `get_client_for_store(store_name)` 取對應 key，`get_default_client()` 取第一把 key
- BaseAgent 統一 File Search + Intent Check 併發邏輯，兩個 agent 共用
- `gemini_with_retry` 包裝器，所有 Gemini 呼叫統一加上重試
- File Search grounding metadata 容錯（有時為 None）
- MongoDB 知識庫檔案儲存，取代本地檔案系統

### Session / 對話管理

- `MongoSessionManager`：Session CRUD，TTL index 自動清理
- `MongoConversationLogger`：對話紀錄、turn_number、rollback、分頁查詢
- Session manager factory lazy singleton，有 MongoDB 就用，否則 fallback 記憶體版
- 修正：`get_mongo_db()` 改為必須傳入明確 db_name，預設 `"jti_app"`（修復 JTI session 落入記憶體版的 bug）
- 一般知識庫 Chat Session（`GeneralChatSessionManager`）也持久化到 MongoDB

### Frontend

- React + Vite，支援 JTI 和 HCIoT 兩個頁面
- 全域 i18n（中/英），per-persona 語言隔離
- TTS 播放控制（播放中顯示 spinner、自動重試、session 重啟自動恢復）
- 對話歷史：多選刪除、日期篩選、重新生成
- AppSelect（Radix UI）取代原生 select
- Esc 關閉所有 modal
- HCIoT workspace：Topic 分類、檔案管理、圖片 picker、CSV 格式提示、樣本下載
