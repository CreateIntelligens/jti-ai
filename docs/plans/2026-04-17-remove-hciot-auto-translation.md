# Remove HCIoT Auto Translation Implementation Plan

> **Status:** Draft
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all HCIoT automatic translation and single-field label fallback so category/topic labels must be provided explicitly in both languages.

**Architecture:** Remove backend Gemini-based label completion in the HCIoT topic admin API, remove frontend helper logic that copies one label into the other language, and delete the standalone HCIoT translation script. Keep the topic/category data model bilingual, but require explicit `zh` and `en` values at creation/edit points.

**Tech Stack:** FastAPI, Pydantic, React, TypeScript, pytest, Vitest

---

### Task 1: Lock backend behavior with tests

**Files:**
- Create: `tests/hciot/test_topics_admin.py`
- Modify: `app/routers/hciot/topics_admin.py`

**Step 1: Write the failing test**

Add tests for:
- creating a topic preserves provided blank `en`/`zh` fields instead of auto-filling them
- updating a topic preserves provided blank `en`/`zh` fields instead of auto-filling them

**Step 2: Run test to verify it fails**

Run: `pytest tests/hciot/test_topics_admin.py -q`
Expected: FAIL because the current router auto-fills missing labels.

**Step 3: Write minimal implementation**

Remove `_fill_missing_translation()` and store request labels exactly as submitted.

**Step 4: Run test to verify it passes**

Run: `pytest tests/hciot/test_topics_admin.py -q`
Expected: PASS

### Task 2: Lock frontend label requirements with tests

**Files:**
- Create: `frontend/tests/hciot/topic-utils.test.ts`
- Modify: `frontend/src/components/hciot/knowledgeWorkspace/topicUtils.ts`

**Step 1: Write the failing test**

Add tests for:
- `buildLabels()` returns `null` unless both `zh` and `en` are non-empty
- `buildLabels()` returns exact trimmed values when both are present

**Step 2: Run test to verify it fails**

Run: `npx vitest run frontend/tests/hciot/topic-utils.test.ts --config frontend/vite.config.ts`
Expected: FAIL because the current helper backfills the missing language.

**Step 3: Write minimal implementation**

Change `buildLabels()` to require both labels and stop copying one field into the other.

**Step 4: Run test to verify it passes**

Run: `npx vitest run frontend/tests/hciot/topic-utils.test.ts --config frontend/vite.config.ts`
Expected: PASS

### Task 3: Update frontend create/edit flows

**Files:**
- Modify: `frontend/src/components/hciot/HciotTopicEditor.tsx`
- Modify: `frontend/src/components/hciot/knowledgeWorkspace/upload/UploadDialog.tsx`
- Modify: `frontend/src/components/hciot/HciotKnowledgeTab.tsx`
- Modify: `frontend/src/components/hciot/HciotKnowledgeWorkspace.tsx`

**Step 1: Update create/edit validation**

Require both `zh` and `en` for:
- new category creation
- new topic creation
- topic/category edits that submit labels

**Step 2: Remove single-language-only upload shortcuts**

Update upload dialog/topic association flows so new category/topic creation collects both labels instead of only Chinese.

**Step 3: Verify flows compile**

Run the targeted frontend tests and type checks needed for touched files.

### Task 4: Remove standalone translation tooling and docs references

**Files:**
- Delete: `scripts/translate_hciot_topics.py`
- Modify: `CHANGELOG.md`

**Step 1: Remove the translation script**

Delete the script so the repo no longer exposes the translation workflow.

**Step 2: Update documentation**

Remove the changelog note describing automatic bilingual translation on save.

### Task 5: Verify end-to-end touched surfaces

**Files:**
- Test: `tests/hciot/test_topics_admin.py`
- Test: `frontend/tests/hciot/topic-utils.test.ts`

**Step 1: Run targeted backend tests**

Run: `pytest tests/hciot/test_topics_admin.py -q`

**Step 2: Run targeted frontend tests**

Run: `npx vitest run frontend/tests/hciot/topic-utils.test.ts --config frontend/vite.config.ts`

**Step 3: Run type check if available for the frontend workspace**

Run the project's existing TypeScript check command covering the touched frontend code.
