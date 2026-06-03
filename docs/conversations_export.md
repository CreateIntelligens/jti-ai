# HCIoT 對話歷史匯出 API 使用文件 (HCIoT Conversation Export API Guide)

本文件說明如何使用後台 API 匯出 HCIoT 系統中的對話歷史，包括認證方式、呼叫端點、支援參數，以及不同格式（完整 vs 簡化）的回傳結果。

---

## 1. 認證機制 (Authentication)

所有對話匯出 API 均需要**管理者權限** (Admin / Super Admin)。可以使用以下三種方式之一進行身份驗證：

> [!WARNING]
> 請將下方的 `<YOUR_ADMIN_API_KEY>` 替換為您在 `.env` 中設定的 `ADMIN_API_KEY` 環境變數值。請勿將真實的金鑰直接提交或記錄於任何公開文件中。

### A. API-Token 請求標頭 (推薦命令列使用)
在 HTTP Header 中帶上 `API-Token`：
```http
API-Token: <YOUR_ADMIN_API_KEY>
```

### B. Authorization Bearer 標頭
在 HTTP Header 中帶上 `Authorization` Bearer Token：
```http
Authorization: Bearer <YOUR_ADMIN_API_KEY>
```

### C. 瀏覽器 Cookie
在瀏覽器中發送請求時，系統會自動附帶名為 `session` 的 Cookie。若您已在後台登入為管理員，直接在瀏覽器輸入網址即可下載。

---

## 2. 匯出 API 端點與參數

### HCIoT 後台管理端點 (HCIoT Admin Export)
* **端點路徑**：`GET /api/hciot-admin/conversations/export`
* **說明**：專門用於 HCIoT 模組的對話紀錄匯出。
* **查詢參數**：
  | 參數名稱 | 類型 | 說明 |
  | :--- | :--- | :--- |
  | `session_ids` | `string` (選填) | 逗號分隔的特定會話 ID，例如：`id1,id2`。若提供，則只匯出這些會話。 |
  | `date_from` | `string` (選填) | 起始日期篩選（含當天，格式例如：`2026-03-01`）。 |
  | `date_to` | `string` (選填) | 結束日期篩選（含當天，格式例如：`2026-03-07`）。 |
  | `simple` | `boolean` (選填) | 設為 `true` 啟用簡化格式（只回傳時間與問答，預設為 `false`）。 |
  | `language` | `string` (選填) | 語言篩選。帶入 `zh` 僅匯出中文會話；帶入 `en` 僅匯出英文會話。未提供則全部匯出。 |

---

## 3. 回傳結果格式說明

### 格式一：簡化格式 (當指定 `simple=true`)
回傳一個平坦的陣列。每個元素代表一個對話 Session，內含 `session_id` 以及依時間排序的問答對清單 `conversations`。

> [!NOTE]
> 簡化格式非常輕量，去除了所有的 Metadata、引用來源 (Citations) 與 Token 詳細 Log，適合快速分析或存檔。

* **回傳範例**：
```json
[
  {
    "session_id": "0d201d81-fdc4-4c87-ad41-92db5814a537",
    "conversations": [
      {
        "timestamp": "2026-03-06T17:21:28.196000",
        "question": "請說明 PRP 的用途",
        "answer": "PRP是用您自己的血液幫助身體修復。醫師會將分離出的高濃度血小板注射到受傷處，促進修復並減輕疼痛。"
      },
      {
        "timestamp": "2026-03-06T17:26:26.365000",
        "question": "PRP 適合哪些疾病？",
        "answer": "PRP適合退化性關節炎、肌腱炎、韌帶損傷、半月板損傷、肩旋轉肌袖撕裂、五十肩等。"
      }
    ]
  }
]
```

### 格式二：完整格式 (預設或 `simple=false`)
回傳包含匯出時間、總對話數、總會話數，以及每個會話的詳細除錯資訊（包含資料庫產生的 `_id`、對話輪數 `turn_number` , RAG 引用文檔 `citations`, Gemini 呼叫的參數 和 `session_snapshot` 等）。

---

## 4. cURL 呼叫範例

### 範例 A: 匯出簡化版的 HCIoT 中文歷史
```bash
curl -H "API-Token: <YOUR_ADMIN_API_KEY>" \
     "http://10.9.0.32:8914/api/hciot-admin/conversations/export?simple=true&language=zh" \
     -o hciot_export_zh_simple.json
```

### 範例 B: 匯出簡化版的 HCIoT 英文歷史
```bash
curl -H "API-Token: <YOUR_ADMIN_API_KEY>" \
     "http://10.9.0.32:8914/api/hciot-admin/conversations/export?simple=true&language=en" \
     -o hciot_export_en_simple.json
```

### 範例 C: 根據日期區間匯出 HCIoT 所有語言的完整歷史
```bash
curl -H "API-Token: <YOUR_ADMIN_API_KEY>" \
     "http://10.9.0.32:8914/api/hciot-admin/conversations/export?date_from=2026-03-01&date_to=2026-03-07" \
     -o hciot_export_march.json
```

### 範例 D: 匯出指定的多個 Session ID (可搭配 `simple=true` 或語言篩選)
```bash
curl -H "API-Token: <YOUR_ADMIN_API_KEY>" \
     "http://10.9.0.32:8914/api/hciot-admin/conversations/export?session_ids=0d201d81-fdc4-4c87-ad41-92db5814a537,f2569874-9153-4a85-bd04-d1d4828d38cb&simple=true" \
     -o hciot_selected_sessions_simple.json
```
