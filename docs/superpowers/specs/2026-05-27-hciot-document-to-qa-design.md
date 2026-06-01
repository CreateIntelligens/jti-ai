# HCIoT 文件轉 Q&A 設計文件

- **日期**：2026-05-27（v1 初版）/ 2026-05-27 增補 v2（整合 tab + fallback）
- **狀態**：v1 已實作完成；v2 進行中
- **分支**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **作者協作對象**：spark.cs.liao
- **預期執行者**：Claude（可接受其他 AI 監督檢視）

---

## 1. 背景與動機

HCIoT 後台目前有兩種知識上傳模式：

1. **Q&A 模式**：上傳 CSV/XLSX，掛在科別/主題下，會產生預設問題 chips
2. **一般文件模式**（勾「一般文件知識（非 Q&A）」）：文件丟進獨立的 doc RAG 通道，不掛 topic、不產生問題

問題：一般文件模式檢索品質與 Q&A 模式分離、難管理、UI 雙軌。實務上希望**所有知識都能以 Q&A 形式管理**（可預覽、可編輯、可單筆隱藏/顯示）。

## 2. 目標

讓使用者**上傳一篇文件（DOCX / TXT / MD）→ 後端用 LLM 自動拆成多組 Q&A → 使用者預覽編輯 → 確認後匯入既有 Q&A 通道**。

此功能完成後，**廢除一般文件 RAG 通道**。

## 3. 設計決策（已與使用者確認）

| 編號 | 議題 | 決定 |
|---|---|---|
| D1 | 舊一般文件 RAG 通道處理 | **廢除**（程式碼移除，舊 Mongo 資料保留不主動清） |
| D2 | LLM 拆 Q&A 處理模式 | **非同步**（FastAPI BackgroundTasks，記憶體 job dict） |
| D3 | 拆完處理 | **預覽 + 編輯 + 確認**（B 方案） |
| D4 | Topic 歸屬 | **上傳時必選**（跟現有 Q&A 上傳一致） |
| D5 | 此路徑匯入的 Q&A 顯示狀態 | **預設 `is_visible=false`**（進 RAG 但不出現在預設問題 chips） |
| D6 | Job 持久化 | **不存 Mongo**，記憶體 dict 即可（重啟丟失可接受） |
| D7 | Worker 模式 | **單 process** 即可，不引入 Celery / RQ |
| D8 | 文件格式 | **DOCX、TXT、MD**（PDF 暫不支援） |
| D9 | Chunking | **不做**——拆 Q&A 本身已是壓縮，超大文件由 LLM 自己挑重點 |
| D10 | 檔案大小上限 | **5 MB** |

## 4. 分階段交付

| 階段 | 範圍 | 驗收方式 |
|---|---|---|
| **階段 1** | 後端：3 個 endpoint + qa_extractor + 記憶體 job dict | curl 走完上傳 → poll → 拿到 qa_pairs → 確認匯入 |
| **階段 2** | 前端：新「文件轉 Q&A」分頁 + 編輯預覽 UI + 確認匯入 | UI 流程走完，匯入後 Q&A 出現在後台、`is_visible=false` |
| **階段 3** | 拆掉舊 doc RAG 通道（程式碼） | 沒有 regression，原本 Q&A 上傳功能不受影響 |

**每階段獨立驗收後再進下一階段。**

---

## 5. 後端 API 規格

所有 endpoint 路徑前綴 `/api/hciot/knowledge`，需 `verify_admin` auth（沿用既有）。

### 5.1 `POST /qa-extract`

**用途**：上傳文件，啟動背景 LLM 拆 Q&A，立刻回 `job_id`。

**請求**：`multipart/form-data`

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `file` | UploadFile | ✓ | `.docx` / `.txt` / `.md`，≤ 5 MB |
| `category_id` | str | ✓ | 目標科別 ID |
| `topic_id` | str | ✓ | 目標主題 ID |
| `category_label` | str | ✓ | 顯示用科別名稱（沿用既有 upload API 慣例） |
| `topic_label` | str | ✓ | 顯示用主題名稱 |
| `language` | str | optional, 預設 `"zh"` | `"zh"` 或 `"en"` |

**成功回應**（200）：

```json
{
  "job_id": "uuid-string",
  "status": "pending"
}
```

**失敗回應**：

- `400` 副檔名不支援 / 檔案大於 5 MB / `category_id` 或 `topic_id` 缺失
- `415` 文件解析失敗（DOCX 損毀等）

### 5.2 `GET /qa-extract/{job_id}`

**用途**：查詢 job 狀態，前端 polling 用。

**成功回應**（200）：

```json
{
  "job_id": "...",
  "status": "pending|running|done|failed",
  "qa_pairs": [
    { "q": "問題1", "a": "回答1" },
    { "q": "問題2", "a": "回答2" }
  ],
  "error": "錯誤訊息（status=failed 時）"
}
```

- `qa_pairs` 僅在 `status="done"` 時存在
- `error` 僅在 `status="failed"` 時存在

**失敗回應**：

- `404` job 不存在或已過期（記憶體 dict 重啟丟失）

### 5.3 `POST /qa-extract/{job_id}/import`

**用途**：使用者編輯完後確認匯入，把 Q&A 寫進既有 topic、觸發 RAG re-index。

**請求**（JSON）：

```json
{
  "qa_pairs": [
    { "q": "編輯後的問題1", "a": "編輯後的回答1" },
    { "q": "新增的問題", "a": "新增的回答" }
  ]
}
```

- 使用者可在前端編輯/新增/刪除任意組，最終以這個陣列為準
- 後端**不**檢查跟 job 原始 `qa_pairs` 是否一致（信任前端）

**成功回應**（200）：

```json
{
  "imported_count": 12,
  "filename": "extracted-{timestamp}.csv",
  "topic_synced": true
}
```

**處理邏輯**：
1. 把 `qa_pairs` 轉成 CSV 格式（欄位至少 `q`, `a`，必要時加 `visible=false`）
2. 走既有 `_insert_uploaded_file` + `_schedule_rag_sync` 路徑
3. **所有列的 `visible` 欄位設為 `false`**（D5）
4. 觸發 `_sync_topic_questions_from_store`，但因為都 hidden，預設問題 chips 不會出現新項目
5. 從記憶體 dict 移除該 job（清理）

**失敗回應**：

- `404` job 不存在
- `400` `qa_pairs` 為空陣列

---

## 6. 後端資料結構

### 6.1 記憶體 Job dict

定義在 `app/services/hciot/qa_extract_jobs.py`：

```
_JOBS: dict[str, QaExtractJob] = {}
```

`QaExtractJob` 欄位（Pydantic model 或 dataclass）：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `job_id` | str | UUID |
| `status` | Literal["pending", "running", "done", "failed"] | |
| `category_id` | str | |
| `topic_id` | str | |
| `category_label` | str | |
| `topic_label` | str | |
| `language` | str | |
| `qa_pairs` | list[dict] \| None | done 時填入 |
| `error` | str \| None | failed 時填入 |
| `created_at` | datetime | |

**併發安全**：FastAPI 預設 async event loop 單 thread，dict 操作天然安全。若未來轉多 worker 需替換為 Redis。

### 6.2 API 函式

```
create_job(category_id, topic_id, ..., language) -> str  # 回 job_id
get_job(job_id) -> QaExtractJob | None
update_job(job_id, **fields) -> None
delete_job(job_id) -> None
```

---

## 7. LLM Prompt 設計

新檔 `app/services/hciot/qa_extractor.py`：

```
async def extract_qa_from_document(
    text: str,
    language: str,
) -> list[dict]:
    """呼叫 Gemini 把文章拆成 Q&A 陣列。"""
```

**Prompt 設計重點**：

- 使用既有 `get_default_client()` 拿 Gemini client（HCIoT 預設 key）
- 使用 **structured output**（response_schema）強制回 `[{q: str, a: str}, ...]`
- 中文 prompt 範例（實作時可微調）：

> 你是醫療衛教知識整理助理。請把以下文章拆解成多組問答（Q&A），符合：
> 1. 每組問題要口語化、像病人或家屬會問的方式
> 2. 答案要完整、可獨立閱讀，不可只引用片段
> 3. 涵蓋全文重點，避免遺漏關鍵資訊
> 4. 答案語氣專業但溫和（衛教助理風格）
> 5. 數量視文章長度決定，通常 5-20 組之間
>
> 文章內容：
> ```
> {text}
> ```

- 語言：依 `language` 切換 system instruction 為中文或英文版

**錯誤處理**：

- LLM 回應解析失敗 → raise，job 標 `failed`
- LLM 回空陣列 → 視為 `failed` with error "未能從文件擷取任何 Q&A"

---

## 8. 後端 router 改動

### 8.1 新增（檔案 `app/routers/hciot/knowledge.py`）

- import `qa_extractor`, `qa_extract_jobs` 模組
- 新增 3 個 endpoint handler（5.1 / 5.2 / 5.3）
- 文件解析輔助：DOCX 用既有 `extract_docx_text`，TXT/MD 直接 decode UTF-8

### 8.2 背景 task 流程

```
async def _run_extract_job(job_id: str, file_bytes: bytes, ext: str, language: str):
    try:
        update_job(job_id, status="running")
        text = parse_document(file_bytes, ext)  # docx/txt/md
        qa_pairs = await extract_qa_from_document(text, language)
        if not qa_pairs:
            update_job(job_id, status="failed", error="...")
            return
        update_job(job_id, status="done", qa_pairs=qa_pairs)
    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
```

由 `POST /qa-extract` 的 `BackgroundTasks.add_task` 觸發。

### 8.3 移除（**階段 3 才執行**）

| 檔案 | 動作 |
|---|---|
| `app/services/rag/document_service.py` | **整檔刪** |
| `app/routers/hciot/knowledge.py` | 移除 `skip_topic` 參數、`_schedule_document_rag_sync`、相關分支 |
| `app/routers/general/knowledge_admin.py` | 移除 doc RAG 相關 endpoint |
| `app/services/general/main_agent.py` | 移除 `"general_doc_knowledge"` from sources |

舊資料：MongoDB 中 `source_type="hciot_doc"` 的 RAG chunks **不主動清除**，留作備份。

---

## 9. 前端 UI 規格

### 9.1 UploadDialog 分頁變更

**現有**（4 tabs，移除「一般文件」勾選後重組）：

```
[上傳知識檔]  [手動輸入]  [上傳圖片]
```

**改為**：

```
[上傳知識檔]  [文件轉 Q&A]  [手動輸入]  [上傳圖片]
```

- 「上傳知識檔」維持原有 CSV/XLSX 批次上傳邏輯，**移除「一般文件知識（非 Q&A）」checkbox**
- 「文件轉 Q&A」為**新分頁**

### 9.2 文件轉 Q&A 分頁流程

**狀態機**：

```
idle  →  uploading  →  pending/running  →  done(editing)  →  importing  →  imported
                                       ↘  failed
```

**UI 區塊**：

1. **科別 / 主題選擇器**（沿用既有 `HciotSelect` 元件）
2. **檔案選擇器**：accept `.docx,.txt,.md`，大於 5 MB 顯示錯誤
3. **上傳/啟動按鈕**：點擊呼叫 `POST /qa-extract`，進 polling 狀態
4. **狀態顯示區**：
   - `pending/running` → spinner + 「正在分析文件…」
   - `failed` → 紅色錯誤訊息 + 「重試」按鈕
   - `done` → 進入編輯預覽
5. **編輯預覽區**（done 後）：
   - 標題：「已從文件擷取 N 組 Q&A，匯入後將預設不顯示在快速問答」
   - 每組 Q&A：兩個 textarea（Q、A），右側「🗑 刪除」
   - 底部：「＋ 新增一組 Q&A」按鈕
   - 動作按鈕：「取消」（清空 job、回到 idle）、「確認匯入」
6. **匯入後**：顯示成功訊息，自動關閉 dialog 或回到 idle

### 9.3 Polling 策略

- 間隔：**1.5 秒**（沿用 TTS polling 慣例）
- Timeout：**5 分鐘**後若仍 pending/running，顯示「處理時間過長，請稍後再試」
- 切換分頁 / 關閉 dialog 時取消 polling（清 timer）

### 9.4 新增 / 修改檔案

| 檔案 | 動作 |
|---|---|
| `frontend/src/components/hciot/knowledgeWorkspace/upload/UploadDialog.tsx` | 加 `'doc'` tab |
| `frontend/src/components/hciot/knowledgeWorkspace/upload/DocumentToQaTab.tsx` | **新建**，整個分頁元件 |
| `frontend/src/components/hciot/knowledgeWorkspace/upload/QaEditPreview.tsx` | **新建**，編輯預覽子元件（可重用） |
| `frontend/src/services/api/hciot.ts` | 加 3 個 API 函式：`createQaExtractJob`, `getQaExtractJob`, `importQaExtractJob` |
| `frontend/src/styles/hciot/workspace-upload.css` | 加上述元件樣式 |

### 9.5 樣式方向

- 沿用 hciot 既有色系（`--hciot-accent` 為主、Plus Jakarta Sans + Noto Sans TC）
- 編輯區用既有 `.hciot-panel` 風格（白底、淺邊框、陰影）
- 每組 Q&A 卡片化，左側細色條表示是 LLM 產出
- 全部用 rem/vh 單位，不用 px（hairline border 除外）

---

## 10. 驗收 Checklist

### 階段 1（後端）

- [ ] `POST /qa-extract` 接受 DOCX/TXT/MD，回 `{job_id, status}`
- [ ] 副檔名不支援 → 400
- [ ] > 5 MB → 400
- [ ] `GET /qa-extract/{job_id}` 在背景處理中時回 `running`
- [ ] 處理完成回 `done` + `qa_pairs`
- [ ] LLM 失敗回 `failed` + `error`
- [ ] `POST /qa-extract/{job_id}/import` 寫入 topic，`is_visible=false`
- [ ] 匯入後 job 從 dict 移除
- [ ] 既有 Q&A CSV 上傳功能完全不受影響

### 階段 2（前端）

- [ ] UploadDialog 出現「文件轉 Q&A」分頁
- [ ] 上傳 DOCX → 顯示處理中 → 顯示編輯預覽
- [ ] 編輯預覽可改 Q、改 A、刪、加
- [ ] 「取消」回到 idle 不寫入
- [ ] 「確認匯入」成功，後台 Q&A 列表出現新資料、`visible=false`
- [ ] 大檔（>5MB）前端先攔截、副檔名錯誤前端先攔截
- [ ] 處理 timeout（5 分鐘）顯示提示
- [ ] 「上傳知識檔」分頁的「一般文件知識」checkbox 已移除

### 階段 3（廢除舊通道）

- [ ] `app/services/rag/document_service.py` 已刪除
- [ ] `skip_topic` 相關程式碼已移除
- [ ] `general_doc_knowledge` source 已從 main_agent 移除
- [ ] 既有 hciot Q&A 上傳、檢索、刪除流程仍正常
- [ ] MongoDB 中既有 `hciot_doc` 資料保留（不主動刪）

---

## 11. 風險與備案

| 風險 | 影響 | 備案 |
|---|---|---|
| LLM 拆出來的 Q&A 品質不佳 | 中 | D3 預覽編輯介面允許手動修正；prompt 後續可優化 |
| 大文件 LLM context 爆炸 | 中 | D9 暫不 chunking；若爆，後續加分段拆解 |
| 記憶體 dict 在 reload/重啟丟 job | 低 | D6 接受重傳，使用者體驗成本低 |
| 多 worker 部署時 dict 不共享 | 低 | 目前單 process；未來轉多 worker 換 Redis |
| 並發大量 LLM 呼叫拖垮後端 | 低 | 短期靠單機 BackgroundTasks 自然 throttle；爆量再加 semaphore |

## 12. 未來擴展（不在本次範圍）

- 不吃PDF 
<!-- - Job 持久化（Redis / Mongo）+ 多 worker -->
- LLM 拆 Q&A 時自動建議 topic 名稱
- 批次上傳多個文件
- 拆 Q&A 流式輸出（stream），讓使用者邊看邊編輯

---

# v2 增補：整合上傳體驗（2026-05-27）

## v2 動機

v1 上線後使用者反饋：

1. **UI 風格不統一**：「上傳知識檔」分頁與「文件轉 Q&A」分頁有兩套不同的 dropzone / 按鈕風格
2. **拖曳缺失**：「文件轉 Q&A」分頁的 dropzone 不支援拖放
3. **沒有「貼上文字」入口**：v1 只接受檔案上傳；使用者希望直接貼整段文字
4. **概念冗餘**：兩個分頁從使用者視角看「都是上傳知識給後台」，分兩個分頁讓人困惑

## v2 設計決策

| 編號 | 議題 | 決定 |
|---|---|---|
| V1 | 兩個分頁是否合併 | **合併成一個 tab「上傳知識」**；FileUploadTab + DocumentToQaTab 整併 |
| V2 | 上傳檔案後是否會立刻打 LLM | **不會**，須由使用者按確認鍵才執行。LLM call 永遠是顯式觸發 |
| V3 | CSV/XLSX vs DOCX/TXT/MD 的路由 | **前端依副檔名分流**（β 方案），不引入後端 gateway。理由：避免抽象成本不對稱（gateway 兩階段要 ~600 行、前端兩行 `match` 解決） |
| V4 | CSV/XLSX 格式錯誤時 | 後端回 **structured error code** `unrecognized_format`；前端顯示「改用 AI 解析」按鈕。使用者按下才把同檔重打 `/qa-extract`（fallback 路徑） |
| V5 | `/qa-extract` 是否支援 CSV/XLSX | **是**——把 CSV/XLSX 當純文字解碼後餵 LLM（XLSX 先 `_xlsx_to_csv_bytes` 轉成 CSV 純文字） |
| V6 | 「貼上文字」endpoint | **廢除** `/qa-extract/text`；前端把 textarea 內容包成虛擬 `.md` File，走 `/qa-extract`（multipart）同一入口 |
| V7 | 字數限制策略 | **後端統一在 `/qa-extract`** 解析完純文字判斷，> 30000 字 → 400。前端文字模式同步顯示字數計當預警 |
| V8 | 單檔 vs 多檔 | **單檔**（與 v1 一致）；原本 FileUploadTab 的 CSV/XLSX 多檔上傳能力**砍除** |

## v2 路由與資料流

### 前端分流規則

```
使用者操作                  → 打哪個 endpoint
─────────────────────────────────────────
上傳 .csv / .xlsx           → POST /upload/      （直接匯入路徑）
   ↓ 後端回 error_code=unrecognized_format
   ↓ UI 顯示「改用 AI 解析」按鈕
   ↓ 使用者按下
   ↓
上傳同檔 .csv / .xlsx       → POST /qa-extract   （AI 路徑 fallback）

上傳 .docx / .txt / .md     → POST /qa-extract
貼上文字                    → 包成 File('pasted.md') 打 POST /qa-extract
```

### `/upload/` 錯誤回應格式（v2 新增）

CSV 解析失敗時，原本回：
```json
{ "detail": "..." }  // 400
```

改為：
```json
{
  "detail": "CSV 格式無法識別 q/a 欄位",
  "error_code": "unrecognized_format",
  "can_fallback_to_ai": true
}
```

前端依 `error_code` 判斷是否顯示 fallback 按鈕。其他 4xx 錯誤（topic 缺失、檔案太大等）維持原行為，不顯示 fallback。

### `/qa-extract` 支援格式擴充（v2 新增）

| 副檔名 | 解析方式 |
|---|---|
| `.docx` | `extract_docx_text(file_bytes)` |
| `.txt` / `.md` | `file_bytes.decode("utf-8")` |
| **`.csv`**（v2 新增）| `file_bytes.decode("utf-8")` 當純文字 |
| **`.xlsx`**（v2 新增）| `_xlsx_to_csv_bytes(file_bytes).decode("utf-8")` |

文字長度超過 30000 字 → 400 `text_too_long`。

## v2 檔案結構（實際）

v1 → v2 過程中前端做了拆解（邏輯不變，只是檔案切細）：

**v1 結構**：
- `DocumentToQaTab.tsx`（單一檔，~460 行）

**v2 結構**：
- `DocumentToQaTab.tsx`（容器 + 狀態機）
- `DocumentToQaSourceForm.tsx`（idle 狀態：mode toggle + file/text 輸入）
- `DocumentToQaStatusView.tsx`（uploading/extracting/importing/success/error 共用 panel）
- `DocumentToQaPreview.tsx`（preview 狀態：編輯介面 + footer）
- `documentToQaTypes.ts`（共用常數：MAX_FILE_SIZE_BYTES, MAX_TEXT_LENGTH, SUPPORTED_EXTS, type DocFileItem 等）

**v2 後端拆解**：
- `app/routers/hciot/knowledge.py`（CSV/XLSX 上傳、檔案 CRUD）
- `app/routers/hciot/qa_extract.py`（**v2 新增**：所有 `/qa-extract*` endpoints 從 knowledge.py 搬出獨立）
- `app/services/hciot/qa_extractor.py`（LLM 呼叫）
- `app/services/hciot/qa_extract_jobs.py`（記憶體 job dict）

## v2 階段交付

| 階段 | 範圍 | 驗收 |
|---|---|---|
| **v2-1** 後端 | `/qa-extract` 加 `.csv/.xlsx` 支援、`/qa-extract` 字數限制 30000、`/upload/` 回 structured error、廢除 `/qa-extract/text` | curl 跑通：CSV 錯誤 fallback、XLSX 走 AI、字數超過擋下 |
| **v2-2** 前端 | 合併 `FileUploadTab` + `DocumentToQaTab` → 單一 `KnowledgeUploadTab`，dropzone accept 全格式單檔，副檔名分流，CSV 失敗顯示「改用 AI 解析」按鈕，貼上文字包成虛擬 File 打 `/qa-extract` | UI 走完：CSV 直匯、CSV 錯誤 fallback、貼上文字、DOCX 走 AI 全部 OK |
| **v2-3** 清理 | 刪除 `FileUploadTab.tsx`、廢除 `createQaExtractJobFromText` API 包裝、後端移除 text endpoint | 沒 regression、TS 編譯綠 |

## v2 風險

| 風險 | 影響 | 備案 |
|---|---|---|
| CSV/XLSX 被 LLM 解讀成奇怪內容（譬如 CSV 純文字含一堆逗號）| 中 | 拆出來的 Q&A 品質低，使用者可在預覽介面手動修正 |
| 貼上文字虛擬 File 名 `pasted.md` 跟真實 `.md` 沒區分 | 低 | 後端不在意來源，純文字解析路徑相同 |
| 砍除 CSV 多檔上傳，舊使用者習慣被破壞 | 中 | 在 dropzone 提示文案標明「單檔」；如有反彈再加回多檔 |
| 字數 30000 對「整本 PDF 改 docx」可能不夠 | 中 | 階段 v2-1 先實作；後續若反彈，加入 chunk-then-merge 邏輯（v3） |

## v2 驗收 Checklist

### v2-1 後端

- [ ] `/qa-extract` 接受 `.csv` → 走 AI 拆 Q&A
- [ ] `/qa-extract` 接受 `.xlsx` → 內部轉 CSV 純文字再餵 AI
- [ ] `/qa-extract` 純文字 > 30000 字 → 400 `text_too_long`
- [ ] `/upload/` CSV 格式錯時回 `{error_code: "unrecognized_format", can_fallback_to_ai: true}`
- [ ] `/qa-extract/text` 已移除（404）
- [ ] 既有 `/qa-extract`（`.docx/.txt/.md`）行為不變

### v2-2 前端

- [ ] 「新增內容」dialog 從 4 tab → 3 tab（合併「上傳知識檔」+「文件轉 Q&A」）
- [ ] 整合 tab 名稱為「上傳知識」
- [ ] Mode toggle `[上傳檔案 | 貼上文字]` 在新 tab 內可用
- [ ] dropzone accept 全格式 `.csv,.xlsx,.docx,.txt,.md`，**單檔**
- [ ] CSV/XLSX 上傳 → 直接匯入成功
- [ ] CSV 格式錯 → 顯示「改用 AI 解析」按鈕 → 按下走 AI 流程
- [ ] DOCX/TXT/MD 上傳 → 走 AI 流程
- [ ] 貼上文字 → 走 AI 流程（後端收到 multipart .md File）
- [ ] CSV 多檔上傳已被砍除

### v2-3 清理

- [ ] `FileUploadTab.tsx` 已刪
- [ ] `createQaExtractJobFromText` API 包裝已移除
- [ ] 後端 `/qa-extract/text` endpoint 已移除
- [ ] TypeScript 編譯綠（`pnpm tsc --noEmit`）
