# Tasks — Extract QA Knowledge Base

每階段一個 commit。每階段完成後跑 [smoke checklist](#smoke-checklist) 才能進下一階段。

---

## Stage 1: Move stateless helpers to `_shared/qa_kb/`

**Risk**: Low (純搬,無邏輯改)

- [x] 建立 `app/services/_shared/qa_kb/__init__.py`
- [x] 搬 `app/services/hciot/csv_utils.py` → `app/services/_shared/qa_kb/csv_utils.py`(內容不變)
- [x] 搬 `app/services/hciot/qa_extract_jobs.py` → `app/services/_shared/qa_kb/extract_jobs.py`(內容不變)
- [x] `app/services/hciot/csv_utils.py` 變 re-export shim
- [x] `app/services/hciot/qa_extract_jobs.py` 變 re-export shim
- [ ] 跑 pytest tests/hciot/
- [ ] Smoke checklist

**Commit**: `refactor: move csv_utils and extract_jobs to _shared/qa_kb`

---

## Stage 2: Extract store base classes

**Risk**: Medium (Mongo collection 行為)

- [x] 建 `app/services/_shared/qa_kb/knowledge_store_base.py`(`QaKbKnowledgeStoreBase` ABC)
- [x] 建 `app/services/_shared/qa_kb/topic_store_base.py`(同上)
- [x] 把 `HciotKnowledgeStore` 改成繼承 base,只覆寫 `NAMESPACE` + `COLLECTION_NAME`
- [x] 把 `HciotTopicStore` 改成繼承 base,同上
- [ ] 跑 pytest tests/hciot/
- [ ] Smoke checklist(特別注意:檔案 CRUD、topic CRUD、has_non_csv_files、get_topic_csv_files)

**Commit**: `refactor: extract qa_kb store base classes`

---

## Stage 3: Extract extractor base + prompts loader

**Risk**: Medium (LLM 呼叫流程)

- [x] 建 `app/services/_shared/qa_kb/extractor_base.py`(generic flow,prompt 透過 callable 注入)
- [x] 建 `app/services/_shared/qa_kb/prompts_loader.py`(generic `load_active_persona_and_role_scope`,attr names 透過參數注入)
- [x] `app/services/hciot/qa_extractor.py` 改成「定義 prompt template」+「呼叫 base flow」
- [x] `app/services/hciot/agent_prompts.py:get_active_persona_and_role_scope` 改成「呼叫 generic loader 並傳 hciot 的 attr names + fallbacks」
- [ ] 跑 pytest
- [ ] Smoke checklist(AI 抽取要實際跑一次)

**Commit**: `refactor: extract qa extractor base and prompts loader`

---

## Stage 4: Build router factory + thin HCIoT routers

**Risk**: Medium-High (API 介面不能斷)

- [x] 建 `app/routers/_shared/qa_kb_router.py`,定義 `QaKbRouterConfig` + `build_qa_kb_router(config)`
- [x] 把 `app/routers/hciot/knowledge.py` 的所有 endpoints 搬進 factory
- [x] 把 `app/routers/hciot/qa_extract.py` 的所有 endpoints 搬進 factory
- [x] `routers/hciot/knowledge.py` 變薄:`router = build_qa_kb_router(QaKbRouterConfig(...))`
- [x] `routers/hciot/qa_extract.py` 同上(看是要併進同一個 factory 還是分開兩個 factory 各自呼叫)
- [x] 確認 `app/main.py` 的 `include_router(...)` 不需改(同樣的 router object)
- [ ] 跑 pytest
- [ ] Smoke checklist (完整跑一遍)
- [ ] API contract diff:用 `openapi.json` 比對前後是否完全一致

**Commit**: `refactor: convert hciot knowledge routers to qa_kb factory`

---

## Stage 5 (NEXT SESSION): Frontend component extraction

**Risk**: High (大規模 rename + props 抽象)

- [x] CSS prefix 全區 rename:`hciot-qa-*` / `hciot-upload-*` / `hciot-file-*` 等 → `qa-workspace-*`
- [x] 建 `frontend/src/components/_shared/qaKnowledgeWorkspace/`
- [x] 搬 `upload/*`, `detail/*`, `explorer/*`, `topicUtils.ts`
- [x] 抽 `QaWorkspaceConfig` props interface(API client、language type、theme)
- [x] HCIoT 變薄 wrapper

**Commit**: `refactor: extract qa knowledge workspace components to shared`

---

## Stage 6 (NEXT SESSION): Frontend API factory

**Risk**: Medium

- [x] 建 `frontend/src/services/api/_shared/qaKnowledge.ts`,API factory 吃 base URL prefix
- [x] `services/api/hciot.ts` 變薄:`createQaKnowledgeApi('/api/hciot-admin/knowledge')`

**Commit**: `refactor: extract qa knowledge api client factory`

---

## Stage 7a: 拆大檔(QaKnowledgeWorkspace.tsx 1072 行)

**Risk**: Medium-High(純結構重構,**行為 byte-for-byte 不變** — 不改 UX、不改 API 呼叫、不改 props 介面)

**Why**:`QaKnowledgeWorkspace.tsx` 是 stage5 搬成的共用公版,1072 行(超過 800 上限)。它會被未來 sub-app clone,現在拆乾淨才好維護。目前是典型「巨型 container」:~25 個 `useState`、~25 個 handler 全擠在一個函式裡。

**拆法**:狀態 + 邏輯抽成 custom hooks,JSX 留在主元件;純函式 helper 移到既有 `topicUtils.ts` 或新 util 檔。目標主元件 < 400 行。

- [x] 抽 `useWorkspaceData(api, language)` hook — files/categories/images state + `refreshWorkspace` / `refreshWorkspaceAfterTopicChange` / `completeUpload`
- [x] 抽 `useFileEditor(...)` hook — editorText/originalText/fileEditable/draft/metadataDirty + `handleSave` / `discardChanges` / `handleSelectFile`
- [x] 抽 `useReindex(api)` hook — reindexing state + `pollReindexStatus` / `handleReindex` / clearReindexTimer + cleanup effect
- [x] 抽 `useExplorerTree(...)` hook — expandedKeys/搜尋/sidebar collapse + `toggleExpanded` / `ensureSelectedPathExpanded` / `handleReorder`
- [x] 抽 `useImageManagement(api)` hook — images 相關 state + `handleDeleteImage` / `handleCleanupUnusedImages` / `handleUploadImageComplete`
- [x] 抽 `useTopicMutations(api)` hook — `handleDeleteTopic` / `handleStartRename` / `handleCommitRename` / `handleCategoryChange` / `handleTopicChange`
- [x] 純函式(`parseExplorerKey` / `splitTopicId` / `moveItem` / `createEmptyTopicDraft`)移到 util 檔
- [x] 主元件只留:組裝 hooks + JSX render + 少量本地 UI state(qaDialogOpen 等)
- [x] hook 檔放 `_shared/qaKnowledgeWorkspace/hooks/`
- [x] `npx tsc --noEmit` 0 error
- [x] `pnpm build` 成功
- [x] Smoke checklist(完整跑一遍 — 這是行為不變的唯一保證)

**驗收鐵則**:重構前後 UI 操作完全一致。任一 smoke 項失敗 → revert。

**Commit**: `refactor: split QaKnowledgeWorkspace into focused hooks`

---

## Stage 7b: 拆大檔(qa_kb_router.py 965 行)

**Risk**: Medium(純結構重構,**API 介面 byte-for-byte 不變** — route 路徑、method、request/response shape 全不變)

**Why**:`app/routers/_shared/qa_kb_router.py` 是 stage4 的 router factory,965 行(逼近 800 上限)。它塞了兩組 endpoint 註冊 + 一整套 module-level helper(topic 同步、CSV 去重、upload 寫入)。會被未來 sub-app clone,拆乾淨才好維護。`_sync_topic_questions_*` / `_resolve_hidden` 剛出過 hidden-questions 覆蓋 bug,抽成獨立模組 + 補強測試最有價值。

**拆法**(helper 不吃閉包,可直接搬成 module-level 函式,route handler 仍呼叫它們):

- [x] 抽 `qa_kb_sync.py` — `_sync_topic_questions_from_store` / `_sync_topic_questions_for_doc` / `_resolve_hidden` / `_get_topic_hidden_questions` / `_existing_topic_questions`(純邏輯,最該抽)
- [x] 抽 `qa_kb_upload.py` — `save_qa_csv_to_topic` / `_filter_csv_rows_by_existing_questions` / `_rewrite_csv_file_with_split_uploads` / split-image filename helper / `_insert_uploaded_file`
- [x] `qa_kb_router.py` 只留 `QaKbRouterConfig` + `build_qa_kb_router` + route 註冊(import 上面兩個模組)
- [x] 目標每檔 < 500 行
- [x] `pytest tests/hciot/` 全綠(特別是 `test_csv_sync_hidden_questions.py`)
- [x] API contract diff:`openapi.json` 比對前後完全一致
- [x] No new Pyright warnings(route handler 的 "not accessed" 是既有誤報,不算)

**驗收鐵則**:API contract 不變。openapi.json diff 為空。

**Commit**: `refactor: split qa_kb_router into sync and upload modules`

---

## Smoke Checklist

每階段 commit 前手動跑一遍。

1. **上傳 CSV**(`q,a` 欄位齊):進指定 topic 的「Q&A 整合」視圖,topic question list 同步
2. **上傳 docx**:走 AI 抽取 → preview → 編輯 + 勾選 visible → 匯入 → 確認 hidden_questions 寫對
3. **貼 CSV 文字**:前端解 → preview → 匯入 → 入庫
4. **貼散文**:走 AI 抽取(跟 #2 同 preview UI)
5. **重複 question 上傳**:回 `skipped_all_duplicates: true`、不建新 doc
6. **刪除檔案**:topic 同步、RAG 同步
7. **編輯 Q&A 整合**:存檔 → topic questions 更新
8. **不指定 category/topic**:不能送出(必填驗證生效)

任一項失敗 → revert commit、修 root cause、重試。

## Definition of Done (整個 change)

- [ ] 後端 stages 1-4 全部 commit
- [ ] 前端 stages 5-6 全部 commit(下個 session)
- [ ] HCIoT smoke checklist 全綠
- [ ] `app/services/_shared/qa_kb/` 有 README 描述「如何 clone 一個新 sub-app」
- [ ] `pytest tests/hciot/` 全綠
- [ ] No new Pyright warnings(pre-existing 不算)
- [ ] OpenSpec change archived
