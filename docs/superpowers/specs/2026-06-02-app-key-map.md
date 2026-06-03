# app→key 映射表（APP_KEY_MAP）實作工單

- **日期**：2026-06-02
- **狀態**：Draft（規劃完成，待實作；交付他人執行）
- **分支 / 工作區**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **預期執行者**：另一位開發者 / AI

---

## 0. 給接手者：當前基準（務必先讀）

實作前 `stores.py` / `gemini_clients.py` 已是「**精確寫死**」版本（本工單要把它改成映射表版）。當前現況：

- `app/services/gemini_clients.py`
  - `resolve_key_index_by_name(name) -> int`：**精確比對**（大小寫不敏感、去頭尾空白）key 名稱，找不到回 `-1`。**保留沿用**。
  - `resolve_key_index_by_keyword(keyword) -> int`：**舊的模糊 substring 比對**，已標 deprecated。**本工單要刪除**。
- `app/routers/general/stores.py`
  - `ManagedStoreConfig` 有 `key_keyword: str` 欄位，目前**寫死完整 key 名稱**（`JTI傑太日煙` / `HCIOT護聯`）。**本工單要移除此欄位**。
  - `MANAGED_STORES` 四筆帶 `key_keyword=...`。
  - `resolve_key_index_for_store(store_name)`：managed store 走 `resolve_key_index_by_name(config.key_keyword)`，-1 時 `logger.warning` + fallback 0。
- `.env`：`GEMINI_API_KEYS` 格式為 `名稱:key` 逗號分隔；現況 index 0=POC1, 1=POC2, 2=JTI傑太日煙, 3=HCIOT護聯, 4=和泰汽車。

**問題（為何要這份工單）**：key 名稱同時寫在 `.env`（GEMINI_API_KEYS）和 `stores.py`（key_keyword）兩處，須逐字同步，是技術債。目標是讓 key 名稱**只存在 `.env` 一處**。

`resolve_key_index_for_store` 的唯一 caller 路徑已盤點：`_dynamic_store_payload`（stores.py:279）→ 對外回傳 store 的 key_index。動態 / 使用者建立的 store 仍走 `key_index` 或 default，不受影響。

## 1. 目標

- key 名稱**只寫在 `.env` 一處**；`stores.py` 不再寫死任何 key 名稱。
- app→key 用一張映射表決定，**完全命中、順序無關**（重排 GEMINI_API_KEYS 不影響）。
- 找不到對應 key → **明確告警**，不靜默用錯 key。
- 啟動時映射有問題 → log 早期可見（不 crash）。

## 2. 映射表格式

`.env` 新增一行：
```
APP_KEY_MAP=jti:JTI傑太日煙,hciot:HCIOT護聯
```
- 格式：`app:key名稱`，逗號分隔多組。
- `app` = managed_app（jti / hciot）；`key名稱` = `GEMINI_API_KEYS` 冒號前的完整名稱。
- general **不列入**（沿用 default 第一把 key，先前決議）。
- 放 `.env` 而非獨立 config：與 GEMINI_API_KEYS 同處，運維一起改，最不易漏同步。

## 3. 改動清單（依相依順序）

### 3.1 新增 `app/services/app_key_map.py`（TDD，先寫測試）
- `load_app_key_map() -> dict[str, str]`：讀 `APP_KEY_MAP` env，parse 成 `{app: key_name}`。格式錯的條目（無冒號、空值）記 `logger.warning` 跳過，不整體崩。app 名稱正規化為小寫去空白。
- `resolve_key_index_for_app(app: str) -> int`：
  1. 查映射表取得 key 名稱；app 不在表 → 回 `-1`。
  2. 用 `gemini_clients.resolve_key_index_by_name(key_name)` 取 index；找不到 → 回 `-1`。
- 純函式，可單元測試（monkeypatch env + mock `gemini_clients.get_key_names` / `resolve_key_index_by_name`），不需 Mongo / 容器。

### 3.2 `app/routers/general/stores.py` 改用映射表
- `ManagedStoreConfig`：**移除 `key_keyword` 欄位**。
- `MANAGED_STORES` 四筆：移除 `key_keyword=...` 參數。
- `resolve_key_index_for_store()`：managed store 分支改呼叫 `app_key_map.resolve_key_index_for_app(config.managed_app)`；回 -1 時維持現有 `logger.warning(...)` + `return 0`（告警訊息改成提示檢查 `APP_KEY_MAP` 與 `GEMINI_API_KEYS`）。
- import `from app.services import app_key_map`。

### 3.3 刪除舊的模糊函式
- `app/services/gemini_clients.py`：**刪除 `resolve_key_index_by_keyword`**（已無 caller；用 `grep -rn resolve_key_index_by_keyword app/` 確認 0 命中後刪）。`resolve_key_index_by_name` 保留。

### 3.4 啟動驗證（可見性，不 crash）
- 在 app 啟動、`gemini_clients.init_registry()` 之後，呼叫一次驗證：對 `load_app_key_map()` 每個 app，用 `resolve_key_index_by_name` 檢查 key 名稱是否存在；任一找不到 → `logger.error` 列出（哪個 app 的哪個 key 名稱沒對到）。放 `app/main.py` lifespan 或 `deps.init_managers()` 附近（跟著 registry 初始化）。

### 3.5 唯讀檢查腳本 `scripts/check_app_key_map.py`
- 在 backend 容器內跑：`docker compose exec backend python scripts/check_app_key_map.py`。
- 印出對照：`app → 映射表指定 key 名稱 → registry 實際 index/名稱`，並掃既有 dynamic store registry 列出各 store 實際綁的 `key_index`，標出與映射不一致者。
- **唯讀**，只報告不改資料。腳本頂端需 `sys.path.insert(0, ...)` 讓 `app` 可 import（參考 `scripts/create_user.py` 寫法）。

### 3.6 測試（TDD）
- 新增 `tests/services/test_app_key_map.py`：parse 正常 / 格式錯跳過 / app 不在表→-1 / key 名稱找不到→-1 / 大小寫去空白 / 多組。
- 更新 `tests/general/test_home_api_compat.py::test_home_can_load_knowledge_store_list`：目前 mock 的是 `resolve_key_index_by_name`，改成 mock `app_key_map.resolve_key_index_for_app`（回 `{"jti":2,"hciot":3}.get(app,-1)`）。斷言 `[store["key_index"] ...] == [2,2,3,3]` 不變。

### 3.7 文件 / memory
- 本檔狀態改為 Done（待 spark 確認後）。
- 更新 `~/.claude` memory `app-key-binding.md`：現況從「stores.py key_keyword 寫死」改為「.env APP_KEY_MAP 映射表，key 名稱單一來源」。

## 4. 不做 / 邊界

- 不動前端（純後端 key 解析）。
- 不自動改既有 store 資料（只提供 3.5 檢查腳本）。
- `APP_KEY_MAP` 未設時：managed store 走 fallback（index 0）+ 告警，系統仍可啟動。
- general / 動態建立的 store 行為不變。

## 5. 驗收標準

- [ ] 後端 `python -m pytest -q` 全綠（含更新後的 test_home_api_compat）。
- [ ] `grep -rn "key_keyword\|resolve_key_index_by_keyword" app/` → **0 命中**（欄位與舊函式皆已刪）。
- [ ] `grep -rn "JTI傑太日煙\|HCIOT護聯" app/` → **0 命中**（stores.py 不再寫死 key 名稱；名稱只在 .env）。
- [ ] 容器內 `python scripts/check_app_key_map.py` 顯示 jti→JTI傑太日煙(index 2)、hciot→HCIOT護聯(index 3)。
- [ ] 故意把 `APP_KEY_MAP` 的某個 key 名稱打錯 → 啟動 log 出現 error、該 app store 的 key_index fallback 0 並有 warning。

## 6. 一句話總結

> 把 app→key 的對應從「stores.py 寫死 key 名稱 + 精確比對」改成「`.env` 的 `APP_KEY_MAP` 單一來源映射表」：key 名稱只存在 `.env` 一處、完全命中、順序無關、找不到明確告警；同時刪除舊的 `key_keyword` 欄位與模糊比對函式。
