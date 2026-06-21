# ESG Dedicated Routers Implementation Plan

> **For agentic workers:** Use test-driven development for every behavior change and verification-before-completion before reporting completion.

**Status:** Draft

**Goal:** Add dedicated ESG chat, prompts, quiz, and quiz-bank service/router layers while preserving the existing General ESG endpoints and baseline quiz behavior.

**Architecture:** ESG becomes a fixed managed app backed by `ManagedAppAgent`, `ManagedChatService`, and `ManagedQuizService`. Dedicated ESG sessions and conversation logs use `esg_app`; prompt/persona configuration remains in the shared control-plane prompt store under ESG-specific fields; quiz-bank data remains in the existing shared quiz collections partitioned by `__esg__`.

**Tech Stack:** FastAPI, Pydantic, Mongo-backed session/log/prompt stores, pytest.

**Git constraint:** Do not stage or commit without explicit user approval. Each task ends with tests and a diff review only.

---

### Task 1: Lock the ESG route and configuration contracts

**Files:**
- Create: `tests/esg/__init__.py`
- Create: `tests/esg/test_dedicated_routers.py`

1. Add failing tests for `ESG_STORE_NAME`, ESG prompt-store fields, dedicated manager getters, agent/quiz config, and all dedicated route methods/paths.
2. Assert the existing General chat and dynamic `__esg__` mechanisms remain mounted.
3. Run the test file and confirm failure is caused by missing ESG modules/contracts.

### Task 2: Extend shared managed-app configuration for ESG

**Files:**
- Modify: `app/services/quiz/config.py`
- Modify: `app/services/general/managed_chat.py`
- Modify: `app/prompts.py`
- Modify: `app/services/db_names.py`
- Modify: `app/services/session/session_manager_factory.py`
- Modify: `app/deps.py`
- Test: `tests/esg/test_dedicated_routers.py`

1. Add `ESG_STORE_NAME`, `ESG_DB_NAME`, ESG prompt/persona/runtime fields, and ESG session/logger factories.
2. Make `ManagedChatConfig.tts_manager_getter` optional and return unmodified chat responses when absent.
3. Add `negative_keywords` to `QuizFlowConfig`; make `ManagedChatService` use configured positive/negative quiz keywords.
4. Warm the ESG session/logger managers during startup.
5. Run the focused tests until these shared contracts pass.

### Task 3: Create the dedicated ESG service layer

**Files:**
- Create: `app/services/esg/__init__.py`
- Create: `app/services/esg/agent_prompts.py`
- Create: `app/services/esg/runtime_settings.py`
- Create: `app/services/esg/main_agent.py`
- Create: `app/services/esg/quiz_flow.py`
- Test: `tests/esg/test_dedicated_routers.py`

1. Copy the current General default persona/rules/welcome into ESG-owned prompt constants so current behavior remains stable but future ESG changes stay isolated.
2. Persist ESG custom personas and runtime settings through flat ESG-specific prompt fields.
3. Configure `EsgMainAgent` with `__esg__`/`__esg__en`, `esg_knowledge`, and no TTS post-processing.
4. Configure quiz copy and keywords exactly from `2026-06-21-esg-prompt-baseline.json`; use a no-op TTS formatter.
5. Run agent/config/runtime tests.

### Task 4: Add the four ESG compatibility routers

**Files:**
- Create: `app/routers/esg/chat.py`
- Create: `app/routers/esg/prompts.py`
- Create: `app/routers/esg/quiz.py`
- Create: `app/routers/esg/quiz_bank.py`
- Modify: `app/main.py`
- Test: `tests/esg/test_dedicated_routers.py`

1. Add `/api/esg/chat/start`, `/chat/message`, history, export, and admin history routes without TTS endpoints.
2. Add `/api/esg/quiz/start` and `/quiz/pause` over `ManagedQuizService`.
3. Add ESG prompt CRUD/runtime routes using the shared persona router factory and ESG-specific storage fields.
4. Add fixed-store quiz-bank adapters for `__esg__`.
5. Mount public/admin and hidden compatibility prefixes symmetrically with JTI.
6. Verify exact method/path contracts and that General routes still exist.

### Task 5: Verify behavior and scope

**Files:**
- Review all files above; do not change unrelated ESG knowledge, frontend, data, or migration work.

1. Run ESG focused tests inside the backend container.
2. Run adjacent JTI migration, General quiz, prompt, session, and quiz-store tests.
3. Run scoped Ruff, `git diff --check`, and an unstaged status review.
4. Keep this plan and the design spec in Draft status unless the user explicitly confirms completion.
