# 對話歷史列表載入過慢 — 診斷與修復方案

- **狀態**: Draft
- **日期**: 2026-06-10
- **分支**: `feat/rag`（worktree `.worktrees/jtai-rag`）
- **症狀**: 後台打開「對話歷史」列表時要等很久（約 12–19 秒）才出結果，前端一直空轉。
- **適用模式**: `jti`、`hciot`（general 因資料量小暫時無感，但寫法相同，須一併修）

---

## 1. 問題本質（已實測坐實）

歷史列表端點宣稱有「分頁」，但實際傳 `page_size=100000`，等於**一次把整個對話庫撈回來**：

1. `get_paginated_session_ids(query=空, page=1, page_size=100000)` — group 出全部 session_id（上千個），分頁形同虛設。
2. `get_logs_for_sessions(session_ids)` — 用 `{"session_id": {"$in": [上千個 id]}}` 把**每個 session 的每一輪對話**全部撈進記憶體，跨 db-tunnel 走網路到 AWS DocumentDB。`$in` 帶上千個值在 DocumentDB 上特別慢。
3. `group_conversations_by_session(all_conversations)` — 再用 Python 把全部重新分組。

列表畫面其實只需要每個 session 的**摘要**（最後一則訊息、標題、輪數、時間），卻把**完整對話內容**也一起撈了，這是最大的浪費。

`45cbf87 fix(history): support DocumentDB conversation pagination` 只修好了 aggregation pipeline 的 DocumentDB 相容性（拆掉 `$facet`），**沒有真的啟用分頁** —— 呼叫端仍寫死 `page_size=100000`。

### 實測數據（2026-06-10，連 AWS DocumentDB）

| DB | docs | sessions | `get_paginated_session_ids`<br>(page_size=100000) | `get_logs_for_sessions`<br>($in 全部) | 單次開啟總計 |
|---|---|---|---|---|---|
| **jti_app** | 3,121 | 1,048 | 1.93s | **10.55s** | ~12.5s |
| **hciot_app** | 4,513 | 2,064 | 3.53s | **15.31s** | ~18.8s |
| general_app | 149 | 70 | 0.16s | 0.50s | ~0.7s |

主兇是 `get_logs_for_sessions`（10–15 秒）。成本隨資料總量線性成長，永遠沒有上限 —— 資料越累積越慢。

---

## 2. 牽涉到的程式位置

### 後端端點（三個 router 同一個壞模式）

- `app/routers/jti/chat.py`
  - L268–272 `get_conversations`（列表，主要慢點）
  - L336–347 `export_conversations`（匯出，同樣 `page_size=100000`，但匯出本來就要全量，**可不動或另議**）
- `app/routers/hciot/chat.py`
  - L200–201 列表
  - L268–270 匯出
- `app/routers/general/chat.py`
  - L408–414 列表

### 資料層（已是 DocumentDB 相容，分頁邏輯本身正確，可重用）

- `app/services/logging/mongo_conversation_logger.py`
  - `get_paginated_session_ids(query, page, page_size)` — L186–233，分頁 pipeline 已正確（拆 data / count 兩段，無 `$facet`）。
  - `get_logs_for_sessions(session_ids)` — L235–250，撈完整對話，**列表不該用它**。
  - `get_session_logs(session_id, limit)` — L120–145，單 session 詳細，**詳情頁用這個**。

### Python 分組 helper

- `app/utils.py`
  - `group_conversations_by_session()` — L64–98，把完整 conversations 分組（列表頁不需要完整內容）。
  - `build_date_query(mode, date_from, date_to)` — L44。
  - `count_session_conversations()` — L180。

### 前端

- `frontend/src/services/api/general.ts`
  - `getGeneralConversations(storeName?)` — L344–348，**沒帶 `page` 參數**。
  - admin URL map — L355–362（`jti-admin/conversations`、`hciot-admin/conversations`、general `chat/history`）。
- 對應的歷史列表 UI 元件需新增分頁控制（頁碼 / 載入更多）。

### 既有索引（足夠，不需新增）

`app/services/mongo_client.py` L120–126：
```
conversations: (session_id, turn_number), (mode, timestamp desc), (timestamp desc), store_name(sparse)
```

---

## 3. 修復方案（建議：完整分頁 + 列表只回摘要）

核心原則：**列表頁只回每個 session 的摘要，完整對話等點進去才撈。**

### 3.1 後端：列表端點改成真分頁 + 摘要

1. 端點接受 query 參數 `page`（預設 1）、`page_size`（預設 20，設上限例如 100）。
2. 用 `get_paginated_session_ids(query, page, page_size)` 取**當頁**的 session_ids（不再寫死 100000）。
3. **不要**用 `get_logs_for_sessions` 撈完整對話。改為對當頁 session_ids 做一個「摘要」aggregation，每個 session 只回：
   - `session_id`
   - `last_active`（最後一輪 timestamp）
   - `first_message_time`（第一輪 timestamp，列表排序/顯示用）
   - `turn_count`（輪數）
   - `preview`：第一則 `user_message`（或最後一則 `agent_response`，依現有 UI 顯示需求挑一個）
4. 回傳維持既有外層結構，但 `sessions` 改成摘要版，並回 `page`、`page_size`、`total_sessions`、`total_pages`，讓前端能翻頁。

> 摘要 aggregation 範例（須只用 DocumentDB 支援的 stage，**禁用 `$facet`**，比照 `get_paginated_session_ids` 的拆法）：
> ```
> [
>   {"$match": {"session_id": {"$in": page_session_ids}}},
>   {"$sort": {"turn_number": 1}},
>   {"$group": {
>     "_id": "$session_id",
>     "first_message_time": {"$first": "$timestamp"},
>     "last_active": {"$last": "$timestamp"},
>     "turn_count": {"$sum": 1},
>     "preview": {"$first": "$user_message"}
>   }}
> ]
> ```
> 建議在 `MongoConversationLogger` 新增一支 `get_session_summaries(session_ids)` 封裝此 pipeline，三個 router 共用。

### 3.2 詳情頁不變

點進單一 session 時，前端打帶 `session_id` 的既有路徑，後端走 `get_session_logs(session_id)`（已存在，L120）撈完整對話。這條路本來就快、不用改。

### 3.3 前端：列表帶分頁

1. `getGeneralConversations` / 對應 jti、hciot 的列表 API 加上 `page`、`page_size` 參數並帶進 query string。
2. 列表 UI 新增分頁控制（頁碼或「載入更多」），改用後端回的 `total_pages` / `total_sessions`。
3. 列表只渲染摘要欄位；點 session 才呼叫詳情 API 取完整對話。

### 3.4 三個 router 一致

jti / hciot / general 的列表端點都套同一套（共用 `get_session_summaries` + 分頁參數）。general 雖然現在快，但同樣寫法、同樣會隨資料量變慢，一併修。

### 3.5 匯出端點（`export_conversations`）

匯出本質上要全量，維持 `get_logs_for_sessions` 是合理的，**本次可不動**。若要優化可改成串流 / 背景任務，另開議題，不在此文件範圍。

---

## 4. 驗收標準

- [ ] jti / hciot 後台打開歷史列表（第一頁）端點回應時間 < 1s（page_size=20）。
- [ ] 翻頁、日期篩選（`date_from` / `date_to`）仍正確。
- [ ] 點進單一 session 仍能看到完整對話（詳情頁不退化）。
- [ ] `total_sessions` / `total_pages` 正確，前端分頁可正常翻到最後一頁。
- [ ] general 模式同樣套用新分頁，行為一致。
- [ ] 不使用 `$facet`（DocumentDB 不支援，會丟 OperationFailure code 304）。
- [ ] 三個 router 共用同一摘要/分頁邏輯，無重複實作。

## 5. 測試

- 後端：對 `get_paginated_session_ids`、新 `get_session_summaries` 寫單元測試（mock collection / 用測試 db）。覆蓋空結果、單頁、跨頁、日期篩選。
- 端點整合測試：列表回摘要結構 + 分頁欄位；詳情回完整對話。
- 手動量測：在 backend 容器內對 jti_app / hciot_app 量第一頁耗時，對照本文件 §1 數據確認改善。

## 6. 注意事項

- 所有 docker / DB 操作須在 **worktree `.worktrees/jtai-rag` 的容器**內進行（容器名 `jtai-rag-backend-1`），連的是 AWS DocumentDB（經 `jtai-rag-db-tunnel-1`）。
- DocumentDB 限制：避免 `$facet`、避免超大 `$in`。分頁要把工作量壓在 DB 端，別把全量資料拉回 Python。
- 套用 .env / 程式變更：`docker compose up -d --force-recreate backend`（單純 restart 不會重載 .env）。
