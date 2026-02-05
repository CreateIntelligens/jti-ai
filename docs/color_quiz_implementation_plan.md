# 色彩測驗擴增計畫

## 目標

在現有 MBTI 測驗架構上，新增「生活品味色彩探索」測驗，兩種測驗並存，不影響現有功能。

---

## 階段一：資料層擴充

### 1.1 新增題庫檔案
- 建立 `data/quiz_bank_color.json`
- 結構與 MBTI 相似，但選項數量不固定（2~5 個）
- 計分改用色系維度：metal, cool, warm, dark, colorful

```json
{
  "quiz_id": "color_taste",
  "title": "生活品味色彩探索",
  "questions": [
    {
      "id": "c1",
      "text": "選擇一個最能代表你個性的詞彙？",
      "weight": 2,
      "options": [
        {"id": "a", "text": "優雅精緻", "score": {"metal": 2}},
        {"id": "b", "text": "清新自然", "score": {"cool": 2}},
        {"id": "c", "text": "熱情奔放", "score": {"warm": 2}},
        {"id": "d", "text": "沉穩內斂", "score": {"dark": 2}},
        {"id": "e", "text": "獨特創意", "score": {"colorful": 2}}
      ]
    }
    // ... 其他題目
  ]
}
```

### 1.2 新增結果對照表
- 建立 `data/color_results.json`
- 包含 5 種色系的標題、描述、推薦文案

---

## 階段二：Model 層修改

### 2.1 修改 Session Model (`app/models/session.py`)

```python
class Session:
    # 新增欄位
    quiz_type: str = "mbti"  # "mbti" | "color"
    color_scores: Dict[str, int] = {}  # {"metal": 0, "cool": 0, ...}
```

### 2.2 修改 SessionStep Enum

```python
class SessionStep(str, Enum):
    WELCOME = "WELCOME"
    QUIZ = "QUIZ"           # 通用測驗中狀態
    QUIZ_DONE = "QUIZ_DONE" # 測驗完成（可能改名為 DONE）
    CHATTING = "CHATTING"
```

---

## 階段三：Tool 層修改

### 3.1 修改 tool_executor.py

#### start_quiz 函數
- 新增 `quiz_type` 參數
- 根據類型載入不同題庫
- 色彩測驗不需隨機抽題（固定 5 題）

#### submit_answer 函數
- 根據 `session.quiz_type` 使用不同計分邏輯
- MBTI：累加維度分數
- Color：累加色系分數

#### calculate_persona 函數（或新增 calculate_color_result）
- MBTI：計算 4 字母結果
- Color：計算最高分色系，處理平手邏輯

---

## 階段四：Router 層修改

### 4.1 修改 mbti.py

#### 關鍵字判斷
```python
# 現有
start_keywords = ['mbti', '測驗', ...]

# 新增色彩測驗關鍵字
color_keywords = ['色彩', '顏色', '保護殼', '配色']
```

#### 測驗類型判斷
- 使用者說「做測驗」→ 預設 MBTI 或詢問
- 使用者說「色彩測驗」「顏色測驗」→ 色彩測驗
- 使用者說「MBTI」→ MBTI 測驗

---

## 階段五：Prompt 層修改

### 5.1 修改 agent_prompts.py

#### System Instruction
- 新增色彩測驗的說明
- 說明兩種測驗的差異
- 測驗結果文案已在 `color_results.json`

---

## 階段六：前端修改（可選）

### 6.1 修改 JtiTest.tsx
- Quick Action 按鈕可選擇測驗類型
- 或新增色彩測驗專用按鈕

### 6.2 修改 locales
- 新增色彩測驗相關翻譯

---

## 不影響現有功能的策略

1. **向後相容**：`quiz_type` 預設為 "mbti"，現有 session 不受影響
2. **獨立題庫**：色彩測驗使用獨立的 JSON 檔案
3. **計分隔離**：使用不同的分數欄位（persona_scores vs color_scores）
4. **漸進式開發**：先完成後端，再更新前端

---

## 檔案修改清單

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `data/quiz_bank_color.json` | 新增 | 色彩題庫 |
| `data/color_results.json` | 新增 | 結果對照表 |
| `app/models/session.py` | 修改 | 新增 quiz_type, color_scores |
| `app/tools/tool_executor.py` | 修改 | 支援雙測驗類型 |
| `app/routers/mbti.py` | 修改 | 關鍵字判斷、類型選擇 |
| `app/services/agent_prompts.py` | 修改 | 新增色彩測驗說明 |
| `frontend/src/locales/*.json` | 修改 | 新增翻譯（可選）|

---

## 預估工作量

- 階段一（資料層）：30 分鐘
- 階段二（Model 層）：15 分鐘
- 階段三（Tool 層）：1 小時
- 階段四（Router 層）：30 分鐘
- 階段五（Prompt 層）：15 分鐘
- 階段六（前端）：30 分鐘（可選）
- 測試與除錯：30 分鐘

**總計：約 3 小時**

---

## 測試計畫

1. 現有 MBTI 測驗功能正常
2. 色彩測驗可正確觸發
3. 計分邏輯正確（包含平手處理）
4. 結果文案正確顯示
5. 中英文切換正常（如適用）
