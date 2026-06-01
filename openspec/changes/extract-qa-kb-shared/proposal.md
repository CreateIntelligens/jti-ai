# Extract QA Knowledge Base to Shared Layer

**Status**: Draft
**Owner**: spark
**Date**: 2026-05-28

## Why

HCIoT 衛教知識庫的功能(topic 分類、Q&A 整合視圖、CSV row-level dedup、AI 文件 → QA 抽取、預設問題顯示/隱藏)準備當成「同類型 sub-app 的公版」 — 之後可能會有其他醫院、教育或客服場景克隆這套。目前所有實作都鎖在 `app/{routers,services}/hciot/`、`frontend/.../components/hciot/`,新 sub-app 要克隆只能 copy-paste 整個目錄,改名後維護兩份。

## What Changes

把 HCIoT knowledge workspace 的核心抽到 `_shared` 層:

- **後端**:`app/services/_shared/qa_kb/` + `app/routers/_shared/qa_kb_router.py` factory
- **前端**:`frontend/src/components/_shared/qaKnowledgeWorkspace/` + CSS prefix `qa-workspace-*`
- **HCIoT**:變薄 wrapper,只保留 hciot-specific config(persona、API prefix、namespace、預設語言)
- **驗收鐵則**:HCIoT 既有行為**byte-for-byte 不變**

不重新設計功能。**這次只是搬家 + 抽介面**,不加新能力,不調整 UX。

## Non-Goals

- 不抽 JTI(JTI 沒有 topic 概念,使用情境不同)
- 不重新設計 hidden_questions、dedup、AI 抽取的行為
- 不調整 Mongo schema(collection 名仍是 hciot-specific)
- 不抽 image upload / explorer tree 的 hciot-only 邏輯(image 跟 hciot 強耦合,等真有第二個用戶再說)

## Scope (Files Touched)

### 後端

| 來源 | 去處 |
|---|---|
| `app/services/hciot/csv_utils.py` | `app/services/_shared/qa_kb/csv_utils.py` |
| `app/services/hciot/qa_extract_jobs.py` | `app/services/_shared/qa_kb/extract_jobs.py` |
| `app/services/hciot/qa_extractor.py` | base 邏輯 → `_shared/qa_kb/extractor_base.py`;prompt template 留在 hciot |
| `app/services/hciot/knowledge_store.py` | base → `_shared/qa_kb/knowledge_store_base.py`;hciot 繼承 + fix `NAMESPACE` |
| `app/services/hciot/topic_store.py` | base → `_shared/qa_kb/topic_store_base.py`;同上 |
| `app/services/hciot/agent_prompts.py:get_active_persona_and_role_scope` | `_shared/qa_kb/prompts_loader.py`(taking attr names as parameters) |
| `app/routers/hciot/knowledge.py` 的 helper + `save_qa_csv_to_topic` | `_shared/qa_kb_router.py` factory `build_qa_kb_router(...)` |
| `app/routers/hciot/qa_extract.py` 的 endpoints | 同上 factory |

### 前端

| 來源 | 去處 |
|---|---|
| `components/hciot/knowledgeWorkspace/upload/*` | `components/_shared/qaKnowledgeWorkspace/upload/*` |
| `components/hciot/knowledgeWorkspace/detail/*` | `components/_shared/qaKnowledgeWorkspace/detail/*` |
| `components/hciot/knowledgeWorkspace/explorer/*` | `components/_shared/qaKnowledgeWorkspace/explorer/*` |
| `components/hciot/knowledgeWorkspace/topicUtils.ts` 等 helper | `components/_shared/qaKnowledgeWorkspace/` |
| `services/api/hciot.ts`(QA-related 部分) | `services/api/_shared/qaKnowledge.ts` factory |
| `styles/hciot/*.css` `.hciot-*` class | `styles/_shared/qa-workspace.css`,prefix 改 `qa-workspace-*` |

## Risks

- **`hciot-*` CSS prefix 改名**會影響任何外部 reference(如果有)。掃過確認只在 hciot 內部用 → 應該安全。
- **factory pattern 後端** 要確保 dependency injection 不破壞 FastAPI 的 dependency override(verify_admin、language extractor)。
- **HCIoT 是 production**,任一階段 commit 後 manual smoke test:上傳 CSV、上傳 docx 走 AI、貼文字、刪檔、編輯、Q&A 整合視圖。

## Stages (Each = One Commit)

見 [tasks.md](./tasks.md)。

## Out of Session Scope

這個 session 只做後端(階段 1-4)。前端(階段 5-6)留下個 session 做 — 因為:
- 後端 API 凍結後,前端的 target 才穩定
- CSS rename 是大規模機械改動,需要乾淨 context

階段 4 完成後,API 介面跟現在**完全相同**(只是 URL 結構不變、回應 schema 不變),前端不需要任何修改即可繼續運作。
