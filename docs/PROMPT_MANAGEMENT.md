# Prompt 管理系統

## 功能說明

每個 Store (知識庫) 可以擁有最多 **3 個自定義 Prompt**，用於控制 AI 的回答風格和行為。

## 資料存儲

- 位置：`data/prompts/`
- 格式：每個 Store 一個 JSON 檔案
- 檔案名稱：`{store_name}.json`

## API 端點

### 1. 列出所有 Prompts
```bash
GET /api/stores/{store_name}/prompts
```

**回應範例：**
```json
{
  "prompts": [
    {
      "id": "prompt_abc123",
      "name": "客服助手",
      "content": "你是一個專業的客服人員...",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "active_prompt_id": "prompt_abc123",
  "max_prompts": 3
}
```

### 2. 建立新 Prompt
```bash
POST /api/stores/{store_name}/prompts
Content-Type: application/json

{
  "name": "技術文檔助手",
  "content": "你是一個技術文檔專家，回答時應該引用具體的文檔內容..."
}
```

### 3. 取得特定 Prompt
```bash
GET /api/stores/{store_name}/prompts/{prompt_id}
```

### 4. 更新 Prompt
```bash
PUT /api/stores/{store_name}/prompts/{prompt_id}
Content-Type: application/json

{
  "name": "新名稱",
  "content": "新的 prompt 內容"
}
```

### 5. 刪除 Prompt
```bash
DELETE /api/stores/{store_name}/prompts/{prompt_id}
```

### 6. 設定啟用的 Prompt
```bash
POST /api/stores/{store_name}/prompts/active
Content-Type: application/json

{
  "prompt_id": "prompt_abc123"
}
```

### 7. 取得當前啟用的 Prompt
```bash
GET /api/stores/{store_name}/prompts/active
```

## 使用流程

1. **建立 Prompt**：為你的 Store 建立自定義 prompt
2. **設定啟用**：選擇要使用的 prompt
3. **開始對話**：呼叫 `/api/chat/start` 時會自動套用啟用的 prompt
4. **進行對話**：AI 的回答會遵循 prompt 的指示

## 範例場景

### 場景 1：客服機器人
```json
{
  "name": "客服機器人",
  "content": "你是一個專業且友善的客服人員。請根據知識庫中的資料回答問題。如果問題超出知識庫範圍，請禮貌地告知用戶。回答時要簡潔明瞭，並提供具體的參考資訊。"
}
```

### 場景 2：技術文檔助手
```json
{
  "name": "技術文檔助手",
  "content": "你是一個技術文檔專家。回答時請：\n1. 引用具體的文檔章節\n2. 提供程式碼範例（如果適用）\n3. 說明技術細節\n4. 如有多種方法，說明各自的優缺點"
}
```

### 場景 3：教學助教
```json
{
  "name": "教學助教",
  "content": "你是一位耐心的教學助教。請用淺顯易懂的方式解釋概念，必要時使用比喻和範例。鼓勵學生思考，並在回答後提出延伸問題促進學習。"
}
```

## 注意事項

- 每個 Store 最多 3 個 Prompt
- 建立第一個 Prompt 時會自動設為啟用
- 刪除啟用中的 Prompt 會自動切換到第一個可用的 Prompt
- Prompt 內容會在開始對話時套用，修改 Prompt 需要重新開始對話才會生效
