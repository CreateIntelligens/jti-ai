# 對話路徑 DB 並發化與 session 快取設計

> Status: Draft
> Date: 2026-06-24
> Branch: feat/rag
> 起因：HCIoT 並發鴨測發現 5 人同時對話延遲飆升 2–3 倍

## 1. 問題

### 1.1 現象（實測）

| 情境 | 延遲 |
|---|---|
| 1 人單獨對話 | ~4s |
| 5 人同時對話 | 每人 8–13s（變慢 2–3 倍） |

所有請求成功（HTTP 200），系統不崩，但並發明顯劣化。

### 1.2 根因（逐項實測排除後）

瓶頸**不在** Gemini、不在 API key、不在 RAG：

| 環節 | 實測 | 是否瓶頸 |
|---|---|---|
| Gemini chat 生成（繞過 HTTP 直打 SDK） | 同 key 5 並發 0.85s 跑完 | ❌ |
| 本地 embedding（BGE-M3，GPU） | 42ms | ❌ |
| LanceDB 檢索 | `search()` 無鎖、本地 | ❌ |
| **MongoDB 每次往返** | **~217ms（偶 366ms）** | ✅ |

真因有兩層：

1. **同步 DB 呼叫塞在 async 路徑**：`app/routers/hciot/chat.py` 的 `async def chat()` 內直接同步呼叫 `session_manager.get_session()`（無 `await`、無 `to_thread`）。同步 PyMongo 往返 ~217ms 期間**整條 event loop 被凍**，所有並發請求一起卡。

2. **session 一律查 DB**：為解多 worker 的 404 失憶，`MongoSessionManager.get_session()` 改成「一律 `find_one` 打 MongoDB」（每次跨海打 us-west-2 DocumentDB）。一次對話有多次 session 操作，累積成單條延遲大頭。

> 註：DB 是 AWS DocumentDB（us-west-2），經 `db-tunnel`（autossh/socat + TLS）連線；~217ms 含跨區物理延遲。

### 1.3 架構約束

- prod 跑 `--workers 2`（`docker/backend/entrypoint.sh`）。
- session 狀態靠 MongoDB 跨 worker 共享（建立即落庫，見 `MongoSessionManager`），多 worker 安全。
- 決議：**維持多 worker**（吃多核、未來好上量），快取層須多 worker 安全。

## 2. 解法總覽（兩階段）

| 階段 | 解什麼 | 改動 | 風險 | 預期效益 |
|---|---|---|---|---|
| **A** | event loop 被同步 DB 凍結（並發互相阻塞） | 小 | 低 | 5 人並發各自接近單人水準 |
| **B** | 單條對話重複跨海抓 DB | 中 | 中 | 單人 ~4s → 2s 級 |

兩階段互補：A 解「並發互相阻塞」，B 解「單條重複往返」。**先做 A、驗證、再評估 B。**

---

## 3. A 階段：DB 呼叫並發化

### 3.1 目標

把對話相關 router 的同步 PyMongo 呼叫包進 `await run_sync(...)`，使其在 thread pool 執行、不再阻塞 event loop。行為不變、多 worker 不變。

`run_sync` 為專案既有工具（`app/services/gemini_service.py`，內部 `asyncio.to_thread`），Gemini 呼叫已沿用同模式。連線池預設 `maxPoolSize=100`，本來就支援並發，只是被同步呼叫卡死。

### 3.2 範圍（全面包所有 router DB 呼叫）

`app/routers/hciot/chat.py` 內所有 endpoint 的同步 DB 呼叫，含主流程與非對話 endpoint：

- `chat()` 主流程：`get_session`（L122）、`get_session_logs`（L137）、`rebuild_session_from_logs`（L141）、`update_session`（L146）、`get_session`（L154）、`log_conversation`（L156）
- `get_conversations` / `delete_conversations` / `export_conversations` 等的 `get_session_logs` / `get_session_summaries` / `get_session_logs_by_mode`（L195/L210/L287）
- `base_agent.py` chat 流程中的同步 `update_session`（L258）與 `_get_or_create_chat_session` 內的 `update_session`（L367）

> `_sync_history_to_db_background`（L285–296）已用 `run_in_executor` 背景化，無需改。

### 3.3 做法

每個同步呼叫點改為：

```python
# 之前（阻塞 event loop）
session = session_manager.get_session(request.session_id)

# 之後（不阻塞）
from app.services.gemini_service import run_sync
session = await run_sync(session_manager.get_session, request.session_id)
```

注意點：
- `run_sync(fn, *args)` 只收位置參數；需 kwargs 的呼叫用 `lambda` 包。
- base_agent 內的同步 `update_session` 位於非 async helper（`_get_or_create_chat_session`）時，需評估是否上推到 async 呼叫端，或就地背景化（與既有 `_sync_history_to_db_background` 一致）。
- 不改 `SessionManager` 介面，不碰 session 儲存邏輯（留給 B）。

### 3.4 驗證（兩者都做）

1. **時間戳量點**：在 chat 路徑加細時間戳，證明並發時 event loop 不再被單一 DB 往返凍住（多條請求的 DB 往返時間區間重疊，而非首尾相接）。
2. **重跑鴨測**：用同一支 5 人並發腳本（scratchpad `hciot_ducktest.sh`）重測，確認每條延遲從 8–13s 降回接近單人（~4–5s）。

### 3.5 不在 A 範圍

- 不引入快取（B）。
- 不改 worker 數。
- 不改 JTI / General（若 A 驗證有效，後續可循同模式推廣；本階段聚焦 HCIoT 主訴）。

---

## 4. B 階段：Redis 共用 session 快取（只規劃，A 完成後再實作）

### 4.1 目標

解 A 解不掉的「單條對話重複跨海抓 DB」。多 worker 下需共用快取層，故用 Redis。

### 4.2 架構

- **Redis 為獨立 compose 服務**（`redis:7-alpine`），**不**塞進 backend 容器：
  - 符合「一容器一職責」；backend 常 `--force-recreate`，獨立 Redis 不會被連帶清快取。
  - 不對外開埠，僅 `expose` 給內網（與 `db-tunnel` 一致），不違反「單一公開埠走 nginx」慣例。
  - backend `depends_on: redis`。
- **讀路徑**：`get_session` 先查 Redis（本地 ms 級）→ miss 才回 DocumentDB → 回填 Redis。
- **寫路徑**：`update_session` 更新 Redis + 背景落庫 MongoDB（或 write-through，待定）。
- **TTL**：對齊現有 session 動態 TTL（`compute_expires_at`），避免快取與 DB TTL 不一致。

### 4.3 待決項（實作前確認）

- write-through vs write-behind（一致性 vs 延遲取捨）。
- 快取失效策略：以 session_id 為 key；更新即覆寫。
- Redis 持久化需求（session 可重建自 DB，快取可為純記憶體 / 容許清空）。

### 4.4 風險

- 快取與 DB 一致性（尤其多 worker 同時寫同一 session）。
- 新增服務的部署/維運成本。
- 需確認 DocumentDB fallback（Atlas 備援）路徑下快取行為一致。

---

## 5. 未來（第三階段備註，非本次範圍）

若要進一步吃多核 + 大幅上量：維持多 worker + Redis 共用 session 已可支撐。真正瓶頸若轉為 DB 寫入吞吐或跨區延遲，再評估 session 儲存就近部署 / 讀寫分離。
