# JTAI — AI 對話平台

基於 Google Gemini 的輕量 AI 對話平台，支援多專案知識庫整合，目前包含 JTI 與 HCIoT 兩個專案。

## 功能特色

- **多專案支援**：JTI、HCIoT 各自獨立的對話流程與知識庫
- **知識庫查詢**：透過 Gemini File Search 回答產品相關問題
- **多 API Key**：支援多把 Gemini API Key，根據 store 自動選對的 client
- **Session 管理**：完整的對話記錄與 MongoDB 持久化
- **TTS 語音**：背景生成語音，不阻塞對話回應
- **管理介面**：Prompt 管理、對話歷史查詢與匯出

## 系統架構

```
Frontend (React + Vite)
       │
       ↓
FastAPI Backend
  ├── JTI Agent     (Gemini File Search + 色彩測驗流程)
  ├── HCIoT Agent   (Gemini File Search)
  ├── Session Manager (MongoDB)
  └── TTS Job Queue (背景執行緒)
       │
       ↓
  Gemini API  ←→  MongoDB
```

## 快速開始

### 1. 環境需求

- Docker & Docker Compose
- Google Gemini API Key（可多把）
- MongoDB

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，至少填入：

```env
GEMINI_API_KEYS=your_key_1,your_key_2
GEMINI_MODEL_NAME=gemini-2.5-flash
MONGODB_URI=mongodb+srv://...
ADMIN_API_KEY=your_admin_key
PORT=8008
```

### 3. 啟動服務

```bash
docker compose up -d
```

- **JTI**: http://localhost:8913/jti
- **HCIoT**: http://localhost:8913/hciot
- **API 文件**: http://localhost:8913/docs

## 專案結構

```
jtai/
├── app/
│   ├── main.py
│   ├── core.py                     # FileSearchManager
│   ├── deps.py                     # 初始化與依賴注入
│   ├── models/
│   ├── routers/
│   │   ├── jti/                    # JTI API 路由
│   │   └── hciot/                  # HCIoT API 路由
│   └── services/
│       ├── gemini_clients.py       # 多 Key registry
│       ├── gemini_service.py
│       ├── base_agent.py           # 共用 Agent 基底
│       ├── jti/                    # JTI 專屬邏輯
│       └── hciot/                  # HCIoT 專屬邏輯
├── frontend/                       # React 前端
├── docker-compose.yml
└── .env.example
```

## 開發

```bash
# 查看 backend logs
docker compose logs -f backend

# 套用 .env / 程式碼異動
docker compose up -d --force-recreate backend

# 進入容器
docker compose exec backend bash

# 跑測試
pytest tests/
```
