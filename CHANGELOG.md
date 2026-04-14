# Changelog

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
- 多語言 Topic 標籤：儲存時自動翻譯缺失的雙語標籤
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
