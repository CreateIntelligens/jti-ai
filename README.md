# JTAI - AI 對話與知識庫平台

JTAI 是一個以 FastAPI、React/Vite、Google Gemini 和本地 RAG 組成的多應用對話平台。現行主要應用包含 JTI 活動助理、HCIoT 醫院衛教助理，以及可綁定知識庫的 OpenAI-compatible API。

系統目前以 self-hosted RAG 為核心：知識庫文件存放於 MongoDB，啟動與文件異動時會以 BAAI/bge-m3 產生 embedding，寫入 LanceDB 進行本地向量檢索，Gemini 主要負責最後的回答生成。

## 功能特色

- **多應用模式**：JTI、HCIoT 與通用知識庫聊天共用後端基礎設施，但各自保有 session、prompt、TTS 與知識庫邏輯。
- **Self-hosted RAG**：FlagEmbedding + BAAI/bge-m3 產生本地 embedding，LanceDB 做主要檢索，MongoDB 做知識庫與向量備份。
- **自動索引同步**：服務啟動時背景 backfill JTI/HCIoT 中英知識庫；知識庫上傳、更新、刪除時會排程同步到 RAG。
- **知識庫管理**：支援上傳、線上預覽、下載、編輯與刪除文字、CSV、Markdown、DOCX 等文件。
- **Session 與歷史紀錄**：MongoDB 持久化 session、conversation logs、分頁查詢、匯出、批次刪除與 rollback 重建。
- **Prompt 與 API Key 管理**：可管理各應用 prompt/runtime settings，也可建立綁定知識庫的 API key。
- **OpenAI-compatible API**：提供 `/v1/chat/completions`，會先查本地 RAG，再呼叫 Gemini 產生回答。
- **TTS 語音**：背景 job 產生語音並以檔案快取；中文會先走 `NORMALIZE_API_URL`，失敗或未設定時 fallback 到本地 regex + OpenCC 流程。
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
  +--> MongoDB                sessions, logs, knowledge stores, image store, vector backup
  +--> TTS API                background audio generation
```

## 快速開始

### 1. 環境需求

- Docker 與 Docker Compose
- Google Gemini API Key，可設定多把
- MongoDB，Atlas 或自架皆可
- NVIDIA GPU + nvidia-container-toolkit 建議用於 BGE embedding；現行 `docker-compose.yml` 預設預留 GPU，CPU-only 環境需要覆寫 compose device reservation 並設定 `EMBEDDING_DEVICE=cpu`

### 2. 設定環境變數

```bash
cp .env.example .env
```

至少需要設定：

```env
GEMINI_API_KEYS=your_key_1,your_key_2
GEMINI_MODEL_NAME=gemini-3.1-flash-lite-preview
MONGODB_URI=mongodb+srv://...
ADMIN_API_KEY=your_admin_key
PORT=8008
```

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
│   │   ├── rag/                        # chunker、retrieval pipeline、backfill service
│   │   ├── vector_store/               # LanceDB primary store、MongoDB vector backup
│   │   ├── session/                    # session managers and factories
│   │   ├── logging/                    # conversation loggers
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
├── docker/
│   ├── backend.Dockerfile              # builder -> deps -> runner image
│   ├── backend-entrypoint.sh           # bind-mount ownership fix, runs as appuser
│   ├── frontend.Dockerfile             # Node + nginx frontend container
│   ├── frontend-start.sh               # generates nginx config and starts Vite
│   └── nginx.conf.template             # single-port routing
├── data/
│   ├── lancedb/                        # LanceDB vector data
│   └── tts_cache/                      # TTS job metadata/audio cache
├── docs/
├── openspec/
├── docker-compose.yml
├── .env.example
└── CHANGELOG.md
```

## 主要 API

- `POST /api/jti/chat/start`, `POST /api/jti/chat/message`
- `POST /api/hciot/chat/start`, `POST /api/hciot/chat/message`
- `GET /api/hciot/topics`
- `GET /api/hciot/images/{image_id}`
- `GET /api/jti-admin/conversations`, `GET /api/hciot-admin/conversations`
- `GET/POST/PUT/DELETE /api/jti-admin/knowledge/...`
- `GET/POST/PUT/DELETE /api/hciot-admin/knowledge/...`
- `GET/POST/PUT/DELETE /api/hciot-admin/images/...`
- `GET/POST/PUT/DELETE /api/hciot-admin/topics/...`
- `GET/POST/PUT/DELETE /api/keys`
- `POST /v1/chat/completions`

完整 request/response schema 請看 `/docs`。

## 知識庫與 RAG 流程

1. Admin API 或前端工作台把知識庫文件寫入 MongoDB。
2. 上傳、更新、刪除會排程同步到 RAG；服務啟動時也會背景掃描 JTI/HCIoT 的 `zh`、`en` 知識庫。
3. CSV 以 row 為 chunk，並會保留 `img` 欄位解析出的 `image_id`；其他文字類文件走 sentence-aware chunking。
4. BGE-m3 產生 embedding 後寫入 LanceDB，並同步一份到 MongoDB vector backup。
5. Chat 或 `/v1/chat/completions` 查詢時會依 `language`、`source_type` 和 distance threshold 篩選檢索結果。
