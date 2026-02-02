# JTI 智慧助手

JTI 品牌的智慧對話系統，整合 MBTI 性格測驗與商品推薦功能。

## 功能特色

- **智慧對話**：基於 Google Gemini 2.5 Flash 的自然語言對話
- **MBTI 測驗**：5 題快速性格測驗（E/I, S/N, T/F, J/P + 隨機題）
- **商品推薦**：根據 MBTI 性格類型推薦適合的 JTI 商品
- **知識庫查詢**：透過 Gemini File Search 回答商品相關問題
- **對話記錄**：完整的 session 管理和對話日誌

## 系統架構

```
┌─────────────┐
│   用戶      │
└──────┬──────┘
       │
       ↓
┌─────────────────────────────────────┐
│          Nginx (Frontend)           │
│    - React UI (Port 8913)           │
│    - /jti 測試頁面                   │
└──────────────┬──────────────────────┘
               │
               ↓
┌──────────────────────────────────────┐
│       FastAPI Backend                │
│  - Session Manager (記憶體)          │
│  - Main Agent (Gemini 對話)          │
│  - Tool Executor (工具執行)          │
└──────────────┬───────────────────────┘
               │
               ↓
        ┌──────────────┐
        │ Gemini API   │
        │ - File Search│
        │ - Chat       │
        └──────────────┘

註：MongoDB 僅用於原專案的 API Key 管理功能，
    MBTI 測驗系統不依賴 MongoDB
```

## 快速開始

### 1. 環境需求

- Docker & Docker Compose
- Google Gemini API Key
- (選用) MongoDB - 僅用於多 API Key 管理，MBTI 功能不需要

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`：

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash
PORT=8913
BACKEND_PORT=8008
NGINX_PORT=8913
```

### 3. 啟動服務

```bash
docker compose up -d
```

服務啟動後：
- **測試頁面**: http://localhost:8913/jti
- **API 文件**: http://localhost:8913/docs

## MBTI 測驗流程

1. 用戶說「玩MBTI」「測驗」「遊戲」等關鍵字
2. Agent 呼叫 `start_quiz` 工具，開始測驗
3. 顯示第 1 題（E/I 維度）
4. 用戶回答 A 或 B
5. Agent 呼叫 `submit_answer` 提交答案
6. 重複步驟 3-5，直到完成 5 題
7. 自動呼叫 `calculate_persona` 計算 MBTI 類型
8. 呼叫 `recommend_products` 推薦商品
9. 結合知識庫資訊，提供完整推薦說明

## API 端點

### MBTI 測驗

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/mbti/session/new` | 建立新 session |
| POST | `/api/mbti/chat` | 對話（自動處理測驗流程）|
| GET | `/jti` | 測試頁面 |

### 原有功能（File Search）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/stores` | 列出所有知識庫 |
| POST | `/api/stores` | 建立新知識庫 |
| POST | `/api/stores/{name}/upload` | 上傳文件 |
| POST | `/api/chat/start` | 開始對話 |
| POST | `/api/chat/message` | 發送訊息 |

## 專案結構

```
jtai/
├── app/
│   ├── main.py                 # FastAPI 主程式
│   ├── models/
│   │   └── session.py          # Session 資料模型
│   ├── routers/
│   │   ├── mbti.py             # MBTI API 路由
│   │   └── jti_test.py         # 測試頁面
│   ├── services/
│   │   ├── main_agent.py       # Gemini Agent 主邏輯
│   │   ├── agent_prompts.py    # System prompts
│   │   ├── session_manager.py  # Session 管理
│   │   └── conversation_logger.py  # 對話日誌
│   ├── tools/
│   │   ├── tool_executor.py    # 工具執行器
│   │   ├── quiz_tool.py        # 測驗工具
│   │   ├── persona_tool.py     # MBTI 計算
│   │   └── products_tool.py    # 商品推薦
│   └── data/
│       └── quiz_bank.json      # 題庫
├── frontend/                   # React 前端
├── logs/
│   └── conversations/          # 對話記錄
├── docker-compose.yml
└── README.md
```

## 對話日誌

系統會自動記錄所有對話到 `logs/conversations/` 目錄：

- **格式**: `YYYYMMDD_HHMMSS_{session_id}.txt` (人類可讀)
- **格式**: `YYYYMMDD_HHMMSS_{session_id}.jsonl` (機器可讀)
- **內容**: 時間戳、用戶訊息、Agent 回應、工具呼叫、Session 狀態

查看最新對話：

```bash
ls -lt logs/conversations/*.txt | head -1 | xargs cat
```

## 技術細節

### Manual Function Calling

本專案使用 **Manual Function Calling** 而非 Automatic Function Calling (AFC)，因為：

1. 需要混用 Function Declarations + File Search
2. AFC 不支援此組合
3. 需要更精細的工具執行控制

### Session 狀態機

```
CHAT → QUIZ → SCORING → RECOMMEND → DONE
```

- **CHAT**: 一般對話
- **QUIZ**: 測驗進行中
- **SCORING**: 計算 MBTI（自動）
- **RECOMMEND**: 推薦商品
- **DONE**: 完成

### 工具列表

1. `start_quiz`: 開始測驗
2. `submit_answer`: 提交答案
3. `get_question`: 取得題目（已整合到 submit_answer）
4. `calculate_persona`: 計算 MBTI（自動觸發）
5. `recommend_products`: 推薦商品
6. **File Search**: Gemini 內建知識庫查詢（非工具）

## 開發說明

### 查看即時 logs

```bash
docker compose logs -f backend
```

### 進入容器

```bash
docker compose exec backend bash
```

### 重啟服務

```bash
docker compose restart backend
```

## 費用

- **Gemini API**: Flash 模型有免費配額
- **File Search**: 免費（注意配額限制）

## 參考資料

- [Gemini API: File search](https://ai.google.dev/gemini-api/docs/file-search)
- [Gemini API: Function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Google AI Studio](https://aistudio.google.com/)
