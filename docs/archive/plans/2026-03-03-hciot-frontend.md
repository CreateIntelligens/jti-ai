# HCIoT Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a new `/hciot` frontend for hospital education Q&A while keeping `/jti` behavior unchanged.

**Architecture:** Add a new `Hciot` page and HCIoT-specific components/styles under dedicated directories, while reusing stable chat/history/prompt-management pieces from the existing frontend. Use the existing general chat/store backend so HCIoT prompts and knowledge files stay isolated from JTI, remove quiz-facing UI, and replace the welcome area with bilingual hospital education topic cards that trigger preset questions.

**Tech Stack:** React 19, TypeScript, Vite, existing general chat/store APIs, i18next localization, existing shared modal/components where safe.

---

### Task 1: Route and Topic Configuration

**Files:**
- Create: `frontend/src/config/hciotTopics.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/zh.json`
- Modify: `frontend/src/locales/en.json`

**Step 1: Write the failing verification target**

Define a pure configuration module for the 14 hospital education topics with bilingual labels and preset prompts. The route target is `/hciot`, and topic prompts must be derived from this config rather than hardcoded inside the page.

**Step 2: Run verification to confirm the route does not exist yet**

Run: `rg -n "hciot" frontend/src/App.tsx frontend/src/locales/zh.json frontend/src/locales/en.json`
Expected: no `/hciot` page wiring and no HCIoT locale keys

**Step 3: Write minimal implementation**

- Add `frontend/src/config/hciotTopics.ts`
- Add `/hciot` route handling in `frontend/src/App.tsx`
- Add HCIoT-specific locale keys in both locale files

**Step 4: Run verification**

Run: `rg -n "hciot" frontend/src/App.tsx frontend/src/config/hciotTopics.ts frontend/src/locales/zh.json frontend/src/locales/en.json`
Expected: `/hciot` route and bilingual locale keys are present

### Task 2: HCIoT Page and UI Shell

**Files:**
- Create: `frontend/src/pages/Hciot.tsx`
- Create: `frontend/src/components/hciot/HciotHero.tsx`
- Create: `frontend/src/components/hciot/HciotTopicGrid.tsx`
- Create: `frontend/src/components/hciot/HciotMessageList.tsx`
- Create: `frontend/src/components/hciot/HciotInputArea.tsx`
- Modify: `frontend/src/pages/Hciot.tsx`

**Step 1: Write the failing verification target**

The new page must preserve chat/history/language/persona flow, remove quiz quick actions and quiz progress, bind to a dedicated HCIoT store, and expose topic cards that send preset prompts immediately.

**Step 2: Run verification to confirm the new page does not exist yet**

Run: `test -f frontend/src/pages/Hciot.tsx; echo $?`
Expected: `1`

**Step 3: Write minimal implementation**

- Create a dedicated `Hciot` page
- Reuse existing general chat/store endpoints
- Use HCIoT-specific welcome/hero/topic-card UI
- Keep edit/regenerate/history interactions
- Remove quiz-specific status rendering and quick actions
- Keep HCIoT store and prompt flow isolated from `/jti`

**Step 4: Run verification**

Run: `rg -n "quick_action_quiz|status_quiz|startChat\\(|sendMessage\\(" frontend/src/pages/Hciot.tsx frontend/src/components/hciot frontend/src/services/api/general.ts`
Expected: HCIoT uses the general chat/store API and does not depend on quiz UI strings

### Task 3: HCIoT Settings and Verification

**Files:**
- Create: `frontend/src/styles/hciot/layout.css`
- Create: `frontend/src/styles/hciot/components.css`
- Modify: `frontend/src/pages/Hciot.tsx`
- Reuse: `frontend/src/components/PromptManagementModal.tsx`
- Verify: `frontend`
- Verify: `tests/hciot/test_api_routes.py`

**Step 1: Write the failing verification target**

HCIoT should have a distinct healthcare-facing visual identity, while `/jti` still renders via its original page and styles.

**Step 2: Run verification to confirm no HCIoT style files exist yet**

Run: `test -d frontend/src/styles/hciot; echo $?`
Expected: `1`

**Step 3: Write minimal implementation**

- Add dedicated HCIoT styles
- Wire them only into the new page
- Keep JTI style imports unchanged

**Step 4: Run verification**

Run:
- `npx tsc --noEmit`
- `npm run build`
- `PYTHONPATH=. pytest tests/hciot/test_api_routes.py -q`

Expected:
- frontend typecheck passes
- frontend build passes if local toolchain is healthy
- backend route test still passes
