# JTAI - AI 對話與知識庫平台

JTAI 是一個以 FastAPI、React/Vite、Google Gemini 和 self-hosted RAG 組成的多應用對話平台。現行主要應用包含 JTI 活動助理、HCIoT 醫院衛教助理，以及可綁定知識庫的 OpenAI-compatible API。

系統主資料庫為 AWS DocumentDB（Atlas 作為啟動時備援），保存知識庫與 session/log 資料，使用 BAAI/bge-m3 產生本地 embedding，寫入 LanceDB 做向量檢索，再由 Gemini 產生最後回答。

## 功能特色

- **多應用模式**：JTI、HCIoT 與通用知識庫聊天共用後端基礎設施，但各自保有 session、prompt、TTS 與知識庫邏輯。
- **Self-hosted RAG**：FlagEmbedding + BAAI/bge-m3 產生本地 embedding，LanceDB 做主要檢索，MongoDB 做知識庫與向量備份。
- **自動索引同步**：服務啟動時背景 backfill JTI/HCIoT 中英知識庫；知識庫上傳、更新、刪除時會排程同步到 RAG。
- **知識庫管理**：支援上傳、線上預覽、下載、編輯與刪除 TXT、Markdown、CSV、DOCX 等文件。權限採 scope 隔離：super_admin / admin 可跨應用管理，一般 user 則可管理自己 scope 所屬應用的知識庫（檔案、圖片、主題），但碰不到其他應用。
- **HCIoT 文件通道**：HCIoT 可上傳一般文件知識（非 Q&A），不掛 topic，走獨立的 `hciot_doc_knowledge` RAG 池。
- **HCIoT 題目顯示控制**：topic 預設問題可逐題隱藏；隱藏只影響前端問題 chips，不影響 RAG 知識檢索。
- **Session 與歷史紀錄**：MongoDB 持久化 session、conversation logs、分頁查詢、匯出、批次刪除與 rollback 重建。對話歷史開放給已登入 user 讀取/匯出（只看自己應用），刪除維持 admin。
- **Prompt 與 API Key 管理**：可管理各應用 prompt/runtime settings。對外 API key 由 admin 發行並綁定知識庫，採 Fernet 加密儲存可事後查看/複製；一般 user 唯讀，只看得到自己可見知識庫的 key。
- **OpenAI-compatible API**：提供 `/v1/chat/completions`，會先查本地 RAG，再呼叫 Gemini 產生回答。
- **TTS 語音**：背景 job 產生語音並以檔案快取；中文會先走 `NORMALIZE_API_URL`，失敗或未設定時 fallback 到本地 regex + OpenCC 流程。
- **DocumentDB 主庫 + Atlas 備援**：主庫不可用時啟動自動 fallback 到 Atlas。可由 super_admin 在前端觸發 DocumentDB → Atlas 同步（JTI/HCIoT 同步自身、General 全域），或災後反向把 Atlas 資料補回主庫（衝突以主庫為準）。詳見 `scripts/README_db_sync.md`。
- **單一入口**：Docker Compose 只對外暴露 `${PORT}`，frontend container 內的 nginx 會代理 API 與前端頁面。

## 系統架構

```text
Browser
  |
  v
Frontend container
  - nginx listens on ${PORT}
  - proxies /api, /v1, /docs, /health to backend
  - proxies page routes to Vite dev server
  |
  v
FastAPI backend
  - JTI runtime, quiz, prompt, knowledge APIs
  - HCIoT runtime, topic, image, prompt, knowledge APIs
  - General chat, prompt, store, API key APIs
  - OpenAI-compatible /v1/chat/completions
  |
  +--> Gemini API             answer generation
  +--> BGE-m3 / FlagEmbedding local embedding
  +--> LanceDB                local vector search
  +--> DocumentDB (primary)   sessions, logs, knowledge stores, image store, vector backup
  +--> Atlas (fallback)       startup fallback when primary unreachable
  +--> TTS API                background audio generation
```

## 快速開始

### 1. 環境需求

- Docker 與 Docker Compose
- Google Gemini API key，可設定多把
- MongoDB，Atlas 或自架皆可
- NVIDIA GPU + nvidia-container-toolkit 建議用於 BGE embedding；現行 `docker-compose.yml` 預設預留 GPU，CPU-only 環境需要覆寫 compose device reservation 並設定 `EMBEDDING_DEVICE=cpu`

### 2. 設定環境變數

```bash
cp .env.example .env
```

至少需要設定：

```env
GEMINI_API_KEYS=your_key_1,your_key_2
GEMINI_MODEL_NAME=gemini-3.1-flash-lite
MONGODB_URI=mongodb+srv://...
ADMIN_API_KEY=your_admin_key
PORT=8008

# 對外 API Key 加密金鑰 (Fernet)，供事後查看/複製已發行的 sk-xxx
# 產生：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
API_ENCRYPTION_KEY=your_fernet_key
```

`gemini-3.1-flash-lite` 是穩定 model id；若要測試 preview model，可自行把 `GEMINI_MODEL_NAME` 改成當前可用的 preview id。

常用選配：

```env
# TTS
TTS_API_URL=http://10.9.0.35:8001/tts_stream
NORMALIZE_API_URL=http://10.9.0.35:8956/normalize
JTI_TTS_CHARACTER=hayley
HCIOT_TTS_CHARACTER=healthy2

# RAG
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cuda
EMBEDDING_BATCH_SIZE=32
LANCEDB_PATH=data/lancedb
LANCEDB_TABLE_NAME=knowledge
RAG_DISTANCE_THRESHOLD=0.85

# Frontend page gate for restricted hosts
VITE_PUBLIC_ALLOWED_PAGES=jti,hciot
VITE_PUBLIC_RESTRICTED_HOSTS=example.com
```

### 3. 啟動服務

```bash
docker compose up -d --build
```

首次啟動會下載 BGE-m3 模型到 `./.hf_cache`，並在背景索引 MongoDB 中的 JTI/HCIoT 知識庫到 `./data/lancedb`。模型下載與首次索引完成前，RAG 相關回應可能會比較慢或暫時沒有檢索結果。

常用入口：

- JTI: http://localhost:8008/jti
- HCIoT: http://localhost:8008/hciot
- API docs: http://localhost:8008/docs
- Health check: http://localhost:8008/health

## 相關文件

- [第三方開源軟體清單](docs/第三方開源軟體清單.md)
- [第三方開源授權與聲明](docs/第三方開源授權與聲明.md)

## 專案結構

```text
jtai/
├── app/
│   ├── main.py                         # FastAPI app、lifespan、health、OpenAI-compatible API
│   ├── deps.py                         # Gemini、prompt、session、TTS manager 初始化
│   ├── api_keys.py                     # API key 建立與驗證
│   ├── auth.py                         # Admin / bearer auth
│   ├── prompts.py                      # Prompt manager
│   ├── routers/
│   │   ├── general/                    # 通用 chat、stores、prompt、API key、knowledge admin
│   │   ├── jti/                        # JTI chat、quiz、quiz-bank、prompt、knowledge
│   │   ├── hciot/                      # HCIoT chat、topic、image、prompt、knowledge
│   │   └── _shared/                    # 共用 persona router factory
│   ├── services/
│   │   ├── embedding/                  # BGE-m3 embedding service
│   │   ├── rag/                        # chunker、retrieval pipeline、backfill、document RAG service
│   │   ├── vector_store/               # LanceDB primary store、MongoDB vector backup
│   │   ├── session/                    # session managers and factories
│   │   ├── logging/                    # conversation loggers
│   │   ├── db_sync/                     # DocumentDB ↔ Atlas 同步核心（forward/reverse，CLI 與 API 共用）
│   │   ├── jti/                        # JTI agent、quiz、knowledge、TTS glue
│   │   ├── hciot/                      # HCIoT agent、topic/image/knowledge stores、TTS glue
│   │   ├── tts_jobs.py                 # shared background TTS job cache
│   │   └── tts_text.py                 # zh TTS normalization helpers
│   ├── tools/jti/                      # quiz tool definitions and executor
│   └── schemas/
├── frontend/
│   ├── src/pages/                      # Jti、Hciot pages
│   ├── src/components/                 # shared UI, settings, history, app-specific panels
│   ├── src/services/api/               # typed API clients
│   └── tests/                          # frontend test files
├── tests/                              # backend unit/integration tests
├── docker/                             # backend/frontend Dockerfiles and nginx template
├── data/                               # LanceDB vector data and TTS cache
├── docs/                               # current docs and archived plans when present
├── openspec/                           # OpenSpec artifacts
├── docker-compose.yml
├── .env.example
└── CHANGELOG.md
```

## 主要 API

Runtime:

- `POST /api/jti/chat/start`, `POST /api/jti/chat/message`
- `POST /api/hciot/chat/start`, `POST /api/hciot/chat/message`
- `POST /api/jti/quiz/start`, `POST /api/jti/quiz/pause`
- `GET /api/hciot/topics/{lang}`
- `GET /api/hciot/topics/{lang}/all`
- `GET /api/hciot/images/{image_id}`
- `POST /v1/chat/completions`

Admin:

- `GET /api/jti-admin/conversations`, `GET /api/hciot-admin/conversations`（讀取/匯出開放給該應用的 user；刪除限 admin）
- `GET/POST/PUT/DELETE /api/jti-admin/knowledge/...`
- `GET/POST/PUT/DELETE /api/hciot-admin/knowledge/...`
- `GET/POST/PUT/DELETE /api/hciot-admin/images/...`
- `POST/PUT/DELETE /api/hciot-admin/topics/...`
- `GET/POST/PUT/DELETE /api/jti-admin/quiz-bank/...`
- `POST /api/admin/rag/reindex`
- `POST /api/admin/db-sync`（DocumentDB ↔ Atlas 同步，限 super_admin）
- `GET/POST/PUT/DELETE /api/keys`

完整 request/response schema 請看 `/docs`。

## 知識庫與 RAG 流程

1. Admin API 或前端工作台把知識庫文件寫入 MongoDB。
2. 上傳、更新、刪除會排程同步到 RAG；服務啟動時也會背景掃描 JTI/HCIoT 的 `zh`、`en` 知識庫。
3. Q&A CSV 以 row 為 chunk，並會保留 `img` 欄位解析出的 `image_id` 與 `url`。
4. HCIoT 一般文件知識（非 Q&A）會走 `DocumentRagService`，用較大的 semantic chunks 寫入 `{app}_doc_knowledge`，不掛 topic、不產生預設問題。
5. BGE-m3 產生 embedding 後寫入 LanceDB，並同步一份到 MongoDB vector backup。
6. Chat 或 `/v1/chat/completions` 查詢時會依 `language`、`source_type` 和 distance threshold 篩選檢索結果。
