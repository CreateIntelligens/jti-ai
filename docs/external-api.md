# 對外 API 串接測試指南

提供「對外 API Key」(`sk-xxx`)給外部系統呼叫聊天 API 的串接方式與 curl 範例。

---

## 1. 前置資訊

| 項目 | 值 |
|------|-----|
| Base URL（對外） | `http://<你的主機>:8913`(經 nginx 代理，只有 `/api/*` 轉後端) |
| 認證方式 | 對外 API Key `sk-xxx`（由 admin 在「對外 Keys」面板簽發） |
| Key 綁定 | 每把 key 綁定**一個知識庫**，呼叫時自動使用，不需手動指定 store |

> 本機/容器內測試可用 `http://<IP>:8913`。
---

## 2. 認證：三種帶 token 的方式（擇一）

```bash
# 1) Authorization header（建議）
-H "Authorization: Bearer sk-xxxxxxxx"

# 2) API-Token header
-H "API-Token: sk-xxxxxxxx"

# 3) query string（會進 log，僅測試用，不建議正式使用）
?token=sk-xxxxxxxx
```

---

## 3. 對話流程（兩步）

1. `POST /api/chat/start` → 取得 `session_id`
2. `POST /api/chat/message` → 帶 `session_id` 與 `message` 開始對話（可重複呼叫接續同一段對話）

---

### 步驟 1：開啟對話 session

```bash
KEY="sk-xxxxxxxx"
BASE="http://<IP>:8913"

curl -s -X POST "$BASE/api/chat/start" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**回應範例：**

```json
{
  "ok": true,
  "prompt_applied": true,
  "session_id": "3f9e330f-b08e-41d5-9ddb-430b515ce0f2"
}
```

> 記下 `session_id`，下一步要用。store 由 key 自動綁定，不需傳。

---

### 步驟 2：送出訊息

```bash
KEY="sk-xxxxxxxx"
BASE="http://<IP>:8913"
SID="貼上上一步拿到的 session_id"

curl -s -X POST "$BASE/api/chat/message" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"你好，請簡單自我介紹\",\"session_id\":\"$SID\"}"
```

**回應範例：**

```json
{
  "answer": "各位釣友大家好，我是沈文程……",
  "session_id": "3f9e330f-b08e-41d5-9ddb-430b515ce0f2",
  "turn_number": 1,
  "citations": [
    {
      "uri": "寶島漁很大之台灣海釣小百科.md",
      "title": "寶島漁很大之台灣海釣小百科.md",
      "text": "……引用到的原文片段……"
    }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `answer` | AI 回覆內容 |
| `session_id` | 本段對話的 ID（接續對話時繼續帶同一個） |
| `turn_number` | 第幾輪對話 |
| `citations` | RAG 引用到的知識庫來源（檔名 + 片段） |

---

## 4. 一鍵測試腳本（start + message 串起來）

把 `KEY` 換成你的 key 後直接貼進終端機執行：

```bash
KEY="sk-xxxxxxxx"
BASE="http://<IP>:8913"

# 1) 開 session 並取出 session_id
SID=$(curl -s -X POST "$BASE/api/chat/start" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

echo "session_id = $SID"

# 2) 送訊息
curl -s -X POST "$BASE/api/chat/message" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"message\":\"你好，請簡單自我介紹\",\"session_id\":\"$SID\"}"
echo
```

---

## 5. 接續對話

用**同一個 `session_id`** 再次呼叫 `/api/chat/message` 即可接續上下文：

```bash
curl -s -X POST "$BASE/api/chat/message" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"message\":\"那要準備哪些釣具？\",\"session_id\":\"$SID\"}"
```

---

## 6. 常見錯誤

| HTTP 狀態 | 意義 | 處理 |
|-----------|------|------|
| `401` | token 缺失或無效 | 檢查 `Authorization` header、key 是否打錯或已被撤銷 |
| `404` | 找不到知識庫 / session | 確認 key 有綁知識庫；session 過期就重新 `start` |
| `403` | 權限不足 | 對外 key 只能聊天，不能呼叫管理 API（`/api/keys` 等） |
| `500` | 伺服器錯誤 | 看後端 log（`logs/general/error.log`） |

---
