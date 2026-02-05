# 色彩測驗實作計畫（取代 MBTI）

## 目標

以「生活品味色彩探索」取代現有 MBTI 測驗。為了維持前端相容性，保留 `/api/mbti` 路由與 `start_quiz` 工具名稱，但行為全部改為色彩測驗。

---

## Phase 1：資料層

### 1.1 題庫與結果
- `data/quiz_bank_color.json`（120 題）
- `data/color_results.json`（5 種色系）

---

## Phase 2：Model 層

### 2.1 Session Model (`app/models/session.py`)
- `quiz_id` 預設為 `color_taste`
- 新增：
  - `color_result_id: Optional[str]`
  - `color_scores: Dict[str, int]`
  - `color_result: Optional[Dict[str, Any]]`
- 移除 MBTI 相關欄位：`persona`、`persona_scores`、`recommended_products`

### 2.2 SessionStep
- 使用：`WELCOME` → `QUIZ` → `SCORING` → `DONE`
- `RECOMMEND` 保留但不再使用

### 2.3 GameMode
- 預設 `COLOR`
- `MBTI` 保留作相容用途

---

## Phase 3：Tool 層

### 3.1 題庫與選題規則 (`app/tools/quiz.py`)
- 改為讀取色彩題庫
- 依 `selection_rules` 抽題：
  - 1 題 `personality`
  - 4 題從 `random_from` 類別中不重複抽取

### 3.2 計分與結果 (`app/tools/color_results.py`)
- 依答案加總 `score`
- 平手以 `tie_breaker_priority` 決定

### 3.3 Tool Executor (`app/tools/tool_executor.py`)
- `start_quiz`：動態顯示 A～E
- `submit_answer`：支援 A～E、1～5、選項文字
- `calculate_color_result`：測驗完成自動呼叫

---

## Phase 4：Router 層

### 4.1 `app/routers/mbti.py`
- 關鍵字改為色彩測驗
- `_judge_user_choice` 支援 A～E
- 移除 `recommend_products`
- 日誌記錄改為 `color_result_id`

---

## Phase 5：Prompt 層

### 5.1 `app/services/agent_prompts.py`
- 說明色彩測驗與結果
- 移除 MBTI 與商品推薦描述
- 維持繁中 TTS 規則

---

## Phase 6：Frontend（必要）

### 6.1 `frontend/src/pages/JtiTest.tsx`
- `mode` 改為 `COLOR`
- 顯示色系結果

### 6.2 `frontend/src/locales/*.json`
- 更新文案與提示

---

## 檔案修改清單

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `data/quiz_bank_color.json` | 新增 | 色彩題庫 |
| `data/color_results.json` | 新增 | 色系結果 |
| `app/models/session.py` | 修改 | 色彩測驗欄位 |
| `app/tools/quiz.py` | 修改 | 色彩選題 |
| `app/tools/color_results.py` | 新增 | 結果計算 |
| `app/tools/tool_executor.py` | 修改 | 支援色彩測驗 |
| `app/routers/mbti.py` | 修改 | 色彩流程 |
| `app/services/agent_prompts.py` | 修改 | 提示詞更新 |
| `frontend/src/pages/JtiTest.tsx` | 修改 | UI 更新 |
| `frontend/src/locales/*.json` | 修改 | 文字更新 |

---

## 測試計畫

1. 題目抽選規則符合 `selection_rules`
2. 計分與平手排序正確
3. 對話流程可正常完成測驗並回傳色系結果
