# ESG 升 app 層級 + 統一題庫 seed 機制

- **狀態**: Draft
- **日期**: 2026-06-20
- **Worktree**: `/home/human/jtai/.worktrees/jtai-rag`（branch `feat/rag`）

## 背景與問題

`start_quiz` 對 ESG store 噴 `list index out of range`。根因連鎖:

1. ESG 是兩個**動態 hash general store**（`store_95028fc06029`=ESG_ZH、`store_b66923e91295`=ESG_EN，綁 key「和泰汽車」），store id 是不透明 hash，**沒有開機自動 seed 路徑**，只能手動跑 `scripts/seed_esg_quiz.py`。
2. 一旦 DB 沒灌題庫，`tool_executor.start_quiz` 拿到空題庫卻硬取 `selected_questions[0]` → IndexError。（已加空題庫防護，回 `{"error": "此知識庫尚未設定測驗題目"}`。）
3. JTI 走 `migrate_quiz_bank()` 開機 seed，但 `QUIZ_BANK_PATHS` 寫死指向**從不存在**的 `quiz_bank_color_*.json`（殭屍路徑）。JTI 題庫是更早用對路徑灌進 DB 的，migrate 現在對 JTI 也沒在 seed。
4. JTI 和 ESG 用**兩套不同**的 seed 機制（migrate vs 獨立 script）。

## 目標

讓 ESG 成為**固定 app**（與 jti/hciot 同構），並讓 JTI/ESG 用**同一套參數驅動、零特例**的開機 seed 機制。行為差異全部由各 app 的題庫 JSON（參數 + 內容）決定，程式碼不含 app 專屬寫死。

## 核心原則（與用戶確認）

- **行為統一 = 一套程式邏輯 + 參數驅動。** 抽題數、維度、結果文案、開場文案都是**資料**（每個 bank 的 metadata），不是程式分支。
- **一種檔案格式**：所有題庫 JSON 一律 `{"quiz_sets": {"<bank_id>": {...}}}` 容器格式，seed 取容器內第一個 bank（`next(iter(data["quiz_sets"].values()))`）。
- **ESG 文案照搬**：seeder 現有的 ESG opening/already_done/results 文案（三立永續那組）原封移進 ESG JSON，內容不變。
- **遷移舊資料**：兩個 ESG hash store 的既有資料搬到 `__esg__`/`__esg__en`。

## 現況盤點（已驗證）

### 題庫檔案
| 檔案 | 結構 | 內容 | 題數 |
|---|---|---|---|
| `data/quiz_bank_jti_{zh,en}.json`（本次新導出） | `{quiz_sets:{jti_quiz:{...}}}` | 預設題庫「生活品味人格探索」（analyst/diplomat/guardian/explorer） | 12 |
| `data/quiz_bank_esg_{zh,en}.json` | `{quiz_sets:{esg_quiz:{...}}}` | 三立 ESG 永續問答（correct 維度） | 10 |
| `data/quiz_bank_{zh,en}.json`（MBTI 孤兒檔） | `{quiz_sets:{mbti_quick:{...}}}` | MBTI，**無程式引用、與 DB 不符** | 12 |
| `data/quiz_bank_color_{zh,en}.json` | 已於 commit `b220751` 刪除（內容 == DB 的 JTI 題庫，已導出為 `quiz_bank_jti_*`） | — | — |

- **MBTI 孤兒檔（`quiz_bank_{zh,en}.json`）**：用戶決定刪除。無任何程式引用。
- DB 裡 `__jti__` 實際在用的題目 == 被刪的 color 題庫（已導出成 `quiz_bank_jti_*.json`，並包成 `quiz_sets` 容器格式）。

### ESG 兩個 hash store 的資料足跡（已掃描全 DB）
| 位置 | 數量 | key 欄位 |
|---|---|---|
| `system_config.knowledge_stores`（store 註冊表） | 2 | `name` |
| `system_config.prompts` | 2 | `store_name` |
| `jti_app.quiz_bank_metadata` | 4 | `store_name` |
| `jti_app.quiz_bank_questions` | 40 | `store_name` |
| `jti_app.quiz_results_metadata` + `quiz_results` | 4 + 4 | `store_name` |
| `general_app.conversations` | 3 | `store_name` |
| LanceDB RAG / general 知識檔 | **0** | —（ESG 尚無知識上傳，無 RAG 要遷移） |

### app 註冊機制
- `app/routers/general/stores.py` 的 `MANAGED_STORES`：固定 app store 清單，目前 `__jti__`/`__jti__en`/`__hciot__`/`__hciot__en`，由 `resolve_managed_store(store_name)` 解析。
- `ManagedStoreConfig` 欄位：`name/display_name/managed_app/managed_language/key_index/key_name`（已支援 `key_name`，ESG 綁「和泰汽車」可用）。
- app↔key 綁定走 `APP_KEY_MAP` 環境變數（格式 `app:key_name`）。

## 設計

### Section 1 — ESG 升 app 層級

**`app/routers/general/stores.py` `MANAGED_STORES`** 加兩列：
```python
ManagedStoreConfig("__esg__",   "ESG 中文",    "esg", "zh", key_name="和泰汽車"),
ManagedStoreConfig("__esg__en", "ESG English", "esg", "en", key_name="和泰汽車"),
```
**`.env` `APP_KEY_MAP`** 加 `esg:和泰汽車`（與 jti/hciot 同機制；`managed_app="esg"` 成為一等值）。

驗收：`resolve_managed_store("__esg__")` 回非 None；`__esg__` 解析到 key「和泰汽車」。

### Section 2 — 統一、參數驅動的開機 seed

**新增一張 app→seed 來源表**（取代 `QUIZ_BANK_PATHS` 殭屍常數），例如：
```python
QUIZ_SEED_TABLE = [
    # (managed_app, store_name, language, json_path)
    ("jti", "__jti__",   "zh", "data/quiz_bank_jti_zh.json"),
    ("jti", "__jti__en", "en", "data/quiz_bank_jti_en.json"),
    ("esg", "__esg__",   "zh", "data/quiz_bank_esg_zh.json"),
    ("esg", "__esg__en", "en", "data/quiz_bank_esg_en.json"),
]
```
> 註：JTI store id 是 `__jti__`/`__jti__en`，**語言維度已含在 store id**（與既有 `MANAGED_STORES` 一致），seed 表用 store_name 直接定位，language 欄位供 metadata 寫入。

**`migrate_quiz_bank()` 改為迴圈跑此表**，對每列：
1. `_load_bank` 從 JSON 取 `quiz_sets` 容器內第一個 bank（統一格式，JTI/ESG 同解析）。
2. bank 的 metadata（`name/description/total_questions/dimensions/tie_breaker_priority/selection_rules`）**全部從 JSON 讀**，不再有 `QUESTIONS_PER_RUN`/`DIMENSIONS` 之類程式常數。
3. `upsert_metadata` / `insert_questions` / `set_active_bank`，帶 `store_name`，**idempotent**（已最新則跳過，沿用既有 `_default_bank_is_outdated` 判斷）。
4. 對應的 quiz results metadata / store prompts（quiz_copy）一併 seed（見 Section 2.5）。

**移除 `scripts/seed_esg_quiz.py`**：邏輯併入統一 seed。

驗收：DB 清空後開機，`__jti__`/`__jti__en`/`__esg__`/`__esg__en` 四個 store 的題庫、results、quiz_copy 全部就位；重複開機不重複寫、不覆蓋使用者自訂 active bank。

### Section 2.5 — ESG 參數回歸 JSON（消除 seeder 寫死）

ESG JSON 目前缺 `selection_rules/dimensions/total_questions/quiz_copy/results`，導致 seeder 硬補。把這些**移進 `quiz_bank_esg_{zh,en}.json`** 的 bank 物件（文案照搬現有）：
```jsonc
{ "quiz_sets": { "esg_quiz": {
  "name": "三立 ESG 永續問答",
  "description": "...",
  "total_questions": 1,
  "dimensions": ["correct"],
  "tie_breaker_priority": ["correct"],
  "selection_rules": { "total": 1 },
  "quiz_copy": {
    "opening":      { "zh": "來測測你對三立永續的了解吧！請選出正確答案：", "en": "Test your knowledge of SET's sustainability journey! Pick the correct answer:" },
    "already_done": { "zh": "你已經作答過囉！...", "en": "You've already answered! ..." }
  },
  "results": { "correct": { "title": "ESG 永續達人", "description": "..." } },
  "questions": [ ... ]
}}}
```
> `quiz_copy`/`results` 文案逐字取自現行 `scripts/seed_esg_quiz.py`（`QUIZ_COPY` / `RESULTS`）。
> JTI 的這些參數已存在其 JSON（`selection_rules:{total:4}`、四維度）。

統一 seed 一律從 bank 讀 `quiz_copy`/`results`/`selection_rules`；JTI/ESG 在 seeder 程式裡長得**完全一樣**。

驗收：seeder 程式中無任何 `ESG`/`QUESTIONS_PER_RUN`/`DIMENSIONS`/`QUIZ_COPY` 專屬常數；ESG 測驗行為（抽 1 題、correct 結果、三立 opening）與遷移前一致。

### Section 3 — 遷移舊 ESG hash store 資料 → `__esg__`/`__esg__en`

一次性 migration（idempotent，可重跑），把兩個 hash store 的資料改 key 到固定 store id：

對應關係：
- `store_95028fc06029`（ESG_ZH）→ `__esg__`
- `store_b66923e91295`（ESG_EN）→ `__esg__en`

逐 collection 改 `store_name`（或註冊表的 `name`）：
| collection | 動作 |
|---|---|
| `system_config.knowledge_stores` | 把兩筆 `name` 改成 `__esg__`/`__esg__en`；或新增固定註冊、停用舊 hash（見「衝突處理」） |
| `system_config.prompts` | `store_name` hash → `__esg__`/`__esg__en` |
| `jti_app.quiz_bank_metadata`/`quiz_bank_questions` | `store_name` hash → 固定（但題庫本就會被統一 seed 覆蓋，遷移後仍以 JSON seed 為準） |
| `jti_app.quiz_results_metadata`/`quiz_results` | `store_name` hash → 固定 |
| `general_app.conversations` | `store_name` hash → 固定（保留歷史對話） |
| LanceDB / general 知識檔 | 無資料，跳過 |

**衝突處理**：固定 store 與唯一索引。`knowledge_stores.name` 是 unique；若直接改 name 撞索引，採「新增 `__esg__` 註冊 + 刪除舊 hash 註冊」而非 in-place rename。quiz_* 的 unique 索引含 `store_name`，改值前先確認無衝突 doc。

**取捨**：題庫/results 遷移後其實會被 Section 2 的統一 seed 重新寫入（內容相同），所以 quiz_* 的遷移主要為了「無縫切換期間不空窗」；**conversations 與 prompts 是真正需要保住的歷史/設定**。

驗收：遷移後 `__esg__`/`__esg__en` 能解析、有 prompt、有題庫、舊對話歷史可查；舊 hash store 不再被解析為 ESG（停用/刪除）。

## 範圍邊界（YAGNI）

- 不改 jti/hciot 既有行為（只在 `MANAGED_STORES`/`APP_KEY_MAP`/seed 表加列）。
- 不動 general 動態 store 機制本身（ESG 只是從動態升為固定，其他動態 store 不變）。
- ESG 無 RAG 知識，不做 RAG/LanceDB 遷移。
- MBTI 孤兒檔直接刪，不轉格式、不保留。

## 測試

- **單元**：`_load_bank` 對 JTI/ESG 同格式都正確取出 bank；統一 seed 對缺/有 active bank、idempotent 重跑的行為。
- **整合**：DB 清空 → 開機 → 四 store 題庫/results/quiz_copy 就位；`start_quiz` 對 `__esg__`/`__esg__en` 正常出題、抽 1 題、correct 結果。
- **遷移**：跑 migration 後資料正確改 key、無 unique 索引衝突、可重跑；舊 hash 停用。
- **回歸**：JTI `start_quiz` 仍抽 4 題、人格多維度結果不變；空題庫防護仍回乾淨錯誤。

## 待實作前確認

- `.env` 的 `APP_KEY_MAP` 由誰維護、ESG 是否確定綁「和泰汽車」key（key_index 4）。
- 遷移舊 ESG store 時，前端目前指向 hash store 的入口（書籤/連結）是否需要保留可達（或一律改走 `__esg__`）。
