# General 主題式 QA 知識庫工作區（搬 HCIoT 上傳頁到 general）

- **狀態**: Draft
- **日期**: 2026-06-18
- **Worktree**: `/home/human/jtai/.worktrees/jtai-rag`（branch `feat/rag`）

## 核心方針

**一律參考 HCIoT 的既有實作，把這套主題式 QA 知識庫工作區做成「每個人的 general 動態 store 都能用」的通用功能。** 行為、驗證規則、UI 全部對齊 HCIoT，不另立規則；唯一的差異是多一個 `store_name` 維度做隔離。HCIoT 怎樣，general 就怎樣。

## 目標

把 HCIoT 的「上傳知識頁面」——其實是一整套**主題式 QA 知識庫工作區**（topics / 圖片 / 合併 CSV 編輯 / 重建索引 / 上傳指定 topic）——搬到 general 動態 store 也能用。

每個 general store 是一個獨立知識庫，要有**自己獨立的一組 topics**（供「快速問答」選塊），上傳檔案時可指定 topic。

### 必須可管理的三塊（用戶明確要求）

工作區內這三項在 general 都要能調整，缺一不可：

1. **QA 內容** — 編輯知識庫的問答內容（合併 CSV 檢視/編輯，`detail/MergedCsvPane`、`MergedCsvTable`）。
2. **上傳** — 上傳知識文件，上傳時可指定 topic（`upload/`）。
3. **塊速問答按鈕（topics）** — 新增/編輯/排序/隱藏 topics（`explorer/` + topic 管理）；這些 topics 就是前台渲染出來的「快速問答」按鈕。

以上三項本就同屬共用 `QaKnowledgeWorkspace`，故全在「整套 QA 工作區」範圍內。

### 塊速問答的內容來源規則（用戶要求，HCIoT 既有行為）

**只有「格式正確、被承認的 QA CSV」才會產生塊速問答（topic 問題按鈕）。** 此規則 HCIoT 已透過共用 `qa_kb` 邏輯實作，general 走同一套即自動繼承，無需額外開發：

- 上傳時 `validate_supported_hciot_csv` 會擋下「有 Q&A 欄位但缺 `q`/`a` 欄」的壞 CSV（回 400，要求改正）；純非-QA CSV / PDF / txt / docx 仍可上傳入庫供 RAG 檢索。
- topic 的問題清單由 `extract_questions_from_csv` + `_sync_topic_questions_from_store` 從**該 topic 底下的 CSV** 抽出。因此只有正確格式的 QA CSV 會貢獻問題 → 才會在前台渲染成塊速問答按鈕；非 QA 檔案即使掛了 topic 也抽不出問題，不產生按鈕。
- 結論：general **不需要**新寫驗證或塊速問答邏輯，只要正確沿用共用 `qa_kb` 的上傳/sync 路徑（並帶上 `store_name` 維度）即可。

## 範圍決策（已與用戶確認）

| 議題 | 決定 |
|------|------|
| 搬移層級 | **整套 QA 工作區**（topics + 圖片 + 合併 CSV + 重建索引），非單純檔案上傳 |
| topic 分隔 | **每個 store 獨立 topics**（以 `store_name` keying，語言固定 `zh`，不分 zh/en） |
| AI QA 抽取 | **關掉**（同 HCIoT：上傳/貼文字直接存原文，交給 RAG 切 chunk），不做 general 的 `qa_extract` 端點 |

## 現況（為什麼這不是純前端薄包裝）

HCIoT 前後端都已抽象化：

- **前端**：`HciotKnowledgeWorkspace` 只是 `_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace` 的薄包裝，靠 `QaWorkspaceApiClient`（~25 個方法）+ `QaWorkspaceConfig` 注入。
- **後端**：`hciot/knowledge.py` 是 `_shared/qa_kb_router.build_qa_kb_router()` 的薄包裝，靠 `QaKbRouterConfig`（`knowledge_store_factory` / `topic_store_factory` / `rag_source_type`）注入。
- HCIoT 用**固定 namespace**：`DB_NAME="hciot_app"`、`NAMESPACE="hciot"`，topic 同理（`hciot_topics` / `hciot_categories`）。

General 是**一個 namespace 內、N 個動態 `store_name`**：

- 用「另一套」舊的 `app/services/knowledge_store.py`（`KnowledgeStore`），以 `store_name` 為 key、`namespace="general"`。
- **沒有** topic store、圖片、合併 CSV。
- RAG backfill（`app/services/rag/backfill.py`）已支援 `general` namespace 並會帶 topic 語意做 chunk，但 general 目前無處存 topic metadata。

核心難點：HCIoT 架構是「一個 app = 一個固定 NAMESPACE」；general 需要「NAMESPACE + `store_name`」兩維 keying。

## 方案：擴充共用 QA-KB base 支援 per-store 維度（方案 A）

順著既有抽象走，讓共用 base 多吃一個可選的 `store_name` 第二維 key。HCIoT/JTI 不傳 → 維持原行為。General 一律傳 `store_name`。

### 後端改動

**1. `app/services/_shared/qa_kb/knowledge_store_base.py`**
- `_query(language, filename, store_name=None)`：當 `store_name` 有值時，filter 加上 `"store_name": store_name`。
- `insert_file(...)`：doc 多寫 `store_name`（None 時不寫該欄，向後相容）。`_resolve_filename` 的唯一性檢查也帶 store_name → 不同 store 可同檔名。
- `list_files` / `get_file` / `delete_file` / `update_*` / `get_topic_csv_files` / `iter_csv_files_with_data` / `has_non_csv_files`：把 `store_name` 透過既有 `**kwargs` 傳進 `_query`。
- 既有 HCIoT/JTI 呼叫不帶 `store_name` → query 不含該欄 → **完全不影響現有資料**。
  - 風險點：舊文件沒有 `store_name` 欄。HCIoT/JTI query 也不含該欄，故仍命中；general query 一定帶 store_name，只命中新資料。無需資料遷移。

**2. `app/services/_shared/qa_kb/topic_store_base.py`**（同樣加 `store_name` 維度）
- 新增 general 專用 store class：`GeneralTopicStore`（`DB_NAME="general_app"`、`COLLECTION_NAME="general_topics"`、`CATEGORY_COLLECTION_NAME="general_categories"`、`NAMESPACE="general"`），所有 topic/category 操作以 `store_name` 為額外 key。
- 對應 `GeneralKnowledgeStore`（`NAMESPACE="general"`，但走新 base）。
  - 注意：現有 general 檔案存在**舊** `KnowledgeStore`（`app/services/knowledge_store.py`），與新 base 的 collection 不同。決策：**新 general QA 工作區走新 base 的 collection**；舊的單檔上傳路徑（Sidebar 那個）維持讀舊 store，兩者並存到後續再收斂。詳見「相容性」。

**3. `app/routers/general/knowledge.py`（新檔）**
- 仿 `hciot/knowledge.py`：用 `build_qa_kb_router()`，但 `QaKbRouterConfig` 的 factory 接 `store_name`。
- 因為 general 的 store_name 是 request 參數（非固定），router 端點需從 query/path 取得 `store_name` 並傳進 factory。`QaKbRouterConfig.knowledge_store_factory` 簽名由 `Callable[[], Any]` 擴成可接 `store_name`；topic factory 由 `Callable[[str|None], Any]`（language）擴成同時吃 `store_name`。
- `rag_source_type="general"`，`include_extract=False`（QA 抽取關閉）。
- 掛載 prefix 例如 `/api/general/stores/{store_name}/knowledge`、`.../topics`、`.../images`。

**4. `app/services/rag/backfill.py`**
- general 的 sync/delete 需帶 `store_name`（目前 general 上傳已走 `sync_to_rag` 把 store_name 當 language 傳；確認 topic 版上傳也照此 keying）。確保 backfill 寫入 LanceDB 時 general 的 doc 帶 `store_name`，檢索才不跨 store 混。

**5. 圖片**
- 仿 `hciot/images.py` 新增 general per-store 圖片端點，store 以 `store_name` keying。圖片 store 同樣加 `store_name` 維度。

### 前端改動

**1. `frontend/src/components/general/GeneralKnowledgeWorkspace.tsx`（新檔）**
- 仿 `HciotKnowledgeWorkspace`：薄包裝 `QaKnowledgeWorkspace`，注入 `generalQaWorkspaceConfig`。
- `QaWorkspaceConfig`：`sourceType: 'general'`、`disableAiQaExtraction: true`、`text: (_l, zh) => zh`。
- `QaWorkspaceApiClient`：每個方法把 `store_name` 帶進對應的 general API 呼叫。

**2. `frontend/src/services/api/general.ts`**
- 新增 per-store 的 QA-KB API：`listGeneralKnowledgeFiles(storeName)`、`listGeneralTopicsAdmin(storeName)`、`uploadGeneralKnowledgeFileWithTopic({storeName,...})`、topic CRUD、合併 CSV、圖片、reindex 等，對齊 `QaWorkspaceApiClient` 介面。

**3. 掛載點（App.tsx）**
- general 主畫面新增「知識庫工作區」入口（tab 或側欄按鈕，仿 HCIoT 的 `workspace==='files'`），`active` 由該入口控制，並把 `currentStore` 當 `store_name` 傳給 `GeneralKnowledgeWorkspace`。
- 只有 admin（`isAdmin`）可見/可管理（對齊現有 `canManageKnowledge`）。
- 沿用 HCIoT 的 `styles/hciot/workspace-upload*.css`（或抽成共用 `styles/_shared/`）。

### 資料 keying 總表

| 維度 | HCIoT | General |
|------|-------|---------|
| namespace | `hciot` | `general` |
| 第二維 key | 無（固定 app） | `store_name` |
| language | zh/en | 固定 zh |
| topics | `hciot_topics`（全 app 共用） | `general_topics`（per store_name） |

## 相容性與風險

- **不破壞 HCIoT/JTI**：base 的 `store_name` 預設 None → query 不含該欄 → 行為與資料完全不變。新增測試鎖定此不變式。
- **general 既有單檔上傳並存**：舊 Sidebar 上傳走舊 `KnowledgeStore`；新 QA 工作區走新 base collection。短期並存，spec 不在此次收斂兩者（避免擴大範圍）。後續可獨立提案遷移。
- **RAG 檢索隔離**：確保 general doc 在 LanceDB 帶 `store_name`，檢索 filter 不跨 store。這是正確性關鍵，需測試覆蓋。

## 測試

- 後端單元：base 加 `store_name` 後，(a) 不帶 store_name 的舊行為不變；(b) 不同 store_name 互不可見；(c) 同檔名跨 store 不衝突。
- 後端整合：general knowledge router 上傳→列檔→指定 topic→刪除→reindex 全流程；topic CRUD per store 隔離。
- RAG：general 檢索只命中該 store 的 chunk。
- 前端：`GeneralKnowledgeWorkspace` 掛載、上傳流程、topic 選擇（手動驗證 + 既有 workspace 測試沿用）。

## 不做（YAGNI）

- 不做 general 的 AI QA 抽取端點（已關閉）。
- 不做 general 多語言（zh/en）切換。
- 不在此次收斂「舊 general 單檔 store」與「新 QA base store」。
