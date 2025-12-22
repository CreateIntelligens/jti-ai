# Gemini File Search

使用 Google Gemini File Search API 建立知識庫並進行語義查詢。

## 功能

- 建立 / 刪除 File Search Store（知識庫）
- 上傳文件（PDF、TXT、DOCX、CSV 等）
- 語義查詢與多輪對話：根據文件內容回答問題
- 提供 CLI 互動介面與現代化 Web UI

## 支援的檔案格式

https://ai.google.dev/gemini-api/docs/file-search?hl=zh-tw#application
https://ai.google.dev/gemini-api/docs/file-search?hl=zh-tw#text

## 快速開始

### 1. 取得 API Key

前往 [Google AI Studio](https://aistudio.google.com/apikey) 建立 API Key。

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，填入 API Key 及選擇模型：

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash
```

### 3. 啟動服務

```bash
docker compose up --build
```

服務啟動後：
- **Web UI**: http://localhost:8008
- **API 文件**: http://localhost:8008/docs

## 使用方式

### Web UI

1. 開啟 http://localhost:8008
2. 建立新的 Store（知識庫）
3. 上傳文件
4. 開始對話

### CLI 互動介面

進入容器後執行：

```bash
docker exec -it gemini-notebook python -m app.cli
```

依照選單操作即可。

### Python 程式碼範例

```python
from app.core import FileSearchManager

manager = FileSearchManager()

# 建立 Store
store_name = manager.create_store("我的知識庫")

# 上傳文件
manager.upload_file(store_name, "document.pdf")

# 開始對話
chat = manager.start_chat(store_name)
response = manager.send_message("這份文件在講什麼？")
print(response.text)

# 刪除 Store
manager.delete_store(store_name)
```

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/stores` | 列出所有 Store |
| POST | `/api/stores` | 建立新 Store |
| DELETE | `/api/stores/{name}` | 刪除 Store |
| GET | `/api/stores/{name}/files` | 列出 Store 中的檔案 |
| DELETE | `/api/files/{name}` | 刪除檔案 |
| POST | `/api/stores/{name}/upload` | 上傳檔案 |
| POST | `/api/chat/start` | 開始對話 Session |
| POST | `/api/chat/message` | 發送訊息 |
| GET | `/api/chat/history` | 取得對話紀錄 |

## 專案結構

```
gemini-notebook/
├── app/
│   ├── main.py           # FastAPI 後端
│   ├── core.py           # 核心邏輯（FileSearchManager）
│   ├── cli.py            # CLI 互動介面
│   └── static/
│       └── index.html    # Web UI
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 費用

- 儲存：免費 (需注意配額限制)
- 查詢：根據使用的模型與 Tokens 計費 (Flash 模型有免費層級)

## 參考資料

- [Gemini API: File search](https://ai.google.dev/gemini-api/docs/file-search)
- [Google AI Studio](https://aistudio.google.com/)