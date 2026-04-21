# JTAI — AI 對話平台

基於 Google Gemini 的輕量 AI 對話平台，支援多專案知識庫整合，目前包含 JTI 與 HCIoT 兩個專案。

## 功能特色

- **多專案支援**：JTI、HCIoT 各自獨立的對話流程與知識庫
- **Self-Hosted RAG**：本地 BGE-m3 向量化 + LanceDB 向量檢索，取代 Gemini File Search
  - 檢索延遲 ~50–100ms（原本 File Search 1–3 秒）
  - 無 API quota 限制、無 grounding 靜默失敗問題
  - MongoDB 做為備援儲存
- **多 API Key**：支援多把 Gemini API Key,根據 store 自動選對的 client
- **Session 管理**:完整對話記錄與 MongoDB 持久化
- **TTS 語音**:背景生成語音,不阻塞對話回應
- **管理介面**:Prompt 管理、對話歷史查詢與匯出

## 系統架構

```
Frontend (React + Vite)
       │
       ↓
FastAPI Backend
  ├── JTI Agent       (RAG 檢索 + 尋找命定前蓋測驗)
  ├── HCIoT Agent     (RAG 檢索)
  ├── RAG Service     (BGE-m3 embedding → LanceDB ANN search)
  ├── Session Manager (MongoDB)
  └── TTS Job Queue   (背景執行緒)
       │
       ├──→ Gemini API         (對話生成)
       ├──→ LanceDB            (本地向量檢索)
       └──→ MongoDB            (Session + 向量備份)
```

## 快速開始

### 1. 環境需求

- Docker & Docker Compose
- NVIDIA GPU + nvidia-container-toolkit（BGE embedding 推薦,CPU 也可跑但較慢）
- Google Gemini API Key（可多把）
- MongoDB（Atlas 或自架）

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`,至少填入：

```env
GEMINI_API_KEYS=your_key_1,your_key_2
GEMINI_MODEL_NAME=gemini-2.5-flash-lite
MONGODB_URI=mongodb+srv://...
ADMIN_API_KEY=your_admin_key
PORT=8008
```

### 3. 啟動服務

```bash
docker compose up -d
```

首次啟動會下載 BGE-m3 模型到 `./.hf_cache`（約 2GB）,之後啟動會直接使用快取。

- **JTI**: http://localhost:8008/jti
- **HCIoT**: http://localhost:8008/hciot
- **API 文件**: http://localhost:8008/docs

### 4. 建立知識庫向量索引

首次啟動後,需要把知識庫文件灌進 LanceDB：

```bash
docker compose exec backend python -m app.services.rag.backfill
```

## 專案結構

```
jtai/
├── app/
│   ├── main.py
│   ├── deps.py                       # 初始化與依賴注入
│   ├── api_keys.py                   # Admin API key 驗證
│   ├── auth.py
│   ├── prompts.py
│   ├── models/
│   ├── schemas/
│   ├── tools/
│   ├── routers/
│   │   ├── general/                  # 共用路由（session、TTS、admin）
│   │   ├── jti/                      # JTI API 路由
│   │   └── hciot/                    # HCIoT API 路由
│   └── services/
│       ├── gemini_clients.py         # 多 Key registry
│       ├── gemini_service.py
│       ├── base_agent.py             # 共用 Agent 基底
│       ├── embedding/                # BGE-m3 embedding 服務
│       ├── vector_store/             # LanceDB + MongoDB 備份
│       ├── rag/                      # Chunker、檢索、backfill
│       ├── knowledge_store.py
│       ├── session/                  # Session 管理
│       ├── tts_jobs.py
│       ├── logging/
│       ├── jti/                      # JTI 專屬邏輯
│       └── hciot/                    # HCIoT 專屬邏輯
├── frontend/                         # React + Vite 前端
├── docker/
│   ├── backend.Dockerfile            # 3-stage build (builder → deps → runner)
│   ├── frontend.Dockerfile
│   └── nginx.conf.template
├── data/
│   └── lancedb/                      # LanceDB 向量資料（持久化）
├── docker-compose.yml
└── .env.example
```

## 開發

```bash
# 查看 backend logs
docker compose logs -f backend

# 套用 .env / 程式碼異動(重要:restart 不會重新載入 .env)
docker compose up -d --force-recreate backend

# 進入容器
docker compose exec backend bash

# 跑測試
pytest tests/

# 重建向量索引(知識庫更新後)
docker compose exec backend python -m app.services.rag.backfill
```

### Worktree 開發

本專案使用 git worktree 做功能開發,請勿直接在 `main` 分支修改：

```bash
# 列出現有 worktree
git worktree list

# 在 worktree 內操作 docker(容器名稱會跟隨目錄名)
cd .worktrees/<name>
docker compose up -d --force-recreate backend
```
