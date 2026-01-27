# 使用者自訂 API Key 功能

## 功能說明

現在使用者可以在前端輸入自己的 Gemini API Key，使用自己的配額連接 Gemini。

## 特點

✅ **多使用者支援** - 每個使用者使用獨立的 API Key 和 Manager  
✅ **安全儲存** - API Key 儲存在瀏覽器 LocalStorage，不會上傳到伺服器資料庫  
✅ **Session 隔離** - 後端為每個 API Key 建立獨立的 FileSearchManager  
✅ **向下相容** - 如果使用者沒有設定 API Key，會使用伺服器的預設配置  

## 使用方法

### 前端

1. 點擊 Header 右上角的 **🔑 我的 API Key** 按鈕
2. 輸入你的 Gemini API Key（從 https://aistudio.google.com/apikey 取得）
3. 點擊「儲存」

之後所有請求都會使用你自己的 API Key。

### 清除 API Key

在「我的 API Key」彈窗中點擊「清除」按鈕，即可刪除已儲存的 API Key，恢復使用伺服器預設配置。

## 技術細節

### 後端實現

- 所有 API 端點增加 `x_gemini_api_key` header 參數
- 新增 `_get_or_create_manager()` 函數，根據 API Key 建立或取得對應的 Manager
- 使用 `user_managers` 字典快取每個 API Key 的 Manager（以 SHA256 hash 為 key）

### 前端實現

- 新增 `UserApiKeyModal` 元件用於設定 API Key
- 修改 `api.ts`，所有請求自動加上 `X-Gemini-Api-Key` header
- API Key 儲存在 `localStorage`（key: `userGeminiApiKey`）

## API 範例

### 使用預設 API Key

```bash
curl http://localhost:8008/api/stores
```

### 使用自訂 API Key

```bash
curl http://localhost:8008/api/stores \
  -H "X-Gemini-Api-Key: YOUR_API_KEY_HERE"
```

## 安全說明

- 使用者的 API Key 只會：
  1. 儲存在使用者瀏覽器的 LocalStorage
  2. 透過 HTTPS 傳送到後端（僅在記憶體中使用）
  3. 用於建立 Gemini API Client

- API Key **不會**：
  - ❌ 儲存在伺服器資料庫
  - ❌ 寫入日誌檔案
  - ❌ 傳送到第三方服務

## 限制

- 後端 `user_managers` 快取在記憶體中，伺服器重啟後會清空
- 如果長時間不使用，建議手動清除 API Key
