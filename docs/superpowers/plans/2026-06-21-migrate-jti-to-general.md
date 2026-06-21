# Migrate JTI to General Shared Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` for each task and `superpowers:verification-before-completion` before reporting completion.

**Status:** Draft

**Goal:** Move JTI chat, quiz, prompt, quiz-bank, and TTS implementation onto reusable General-layer runtime components while preserving every existing JTI URL and request/response schema.

**Architecture:** Keep `app/routers/jti/*` as compatibility adapters. Shared behavior lives under `app/services/general/*` or router factories under `app/routers/general/*`; JTI injects its session manager, logger, prompt/quiz configuration, TTS manager, and fixed stores (`__jti__`, `__jti__en`). Existing JTI persistence remains in place so deployment does not strand sessions or history. General dynamic-store behavior remains unchanged.

**Tech Stack:** FastAPI, Pydantic, pytest, Mongo-backed session/prompt/quiz stores.

**Git constraint:** Do not stage or commit without explicit user approval. Each task ends with tests and a diff review only.

---

### Task 1: Move shared quiz runtime out of JTI

**Files:**
- Create: `app/services/general/quiz_runtime.py`
- Create: `app/services/general/quiz_helpers.py`
- Delete: `app/services/jti/runtime_quiz_flow.py`
- Delete: `app/services/jti/quiz_helpers.py`
- Modify imports in `app/routers/general/chat.py`, `app/routers/jti/chat.py`, `app/routers/jti/quiz.py`
- Modify tests that patch the old module paths
- Test: `tests/general/test_jti_general_migration.py`

1. Add a failing import-boundary test requiring the General module paths and rejecting production imports from the old JTI paths.
2. Run the test and confirm failure is caused by missing General modules.
3. Move the modules without behavior changes and update all production/test patch paths.
4. Run the new boundary test plus JTI/general quiz tests.

### Task 2: Replace app-specific TTS modules with a General factory

**Files:**
- Create: `app/services/general/tts.py`
- Delete: `app/services/jti/tts.py`
- Delete: `app/services/hciot/tts.py`
- Modify: `app/deps.py`
- Modify: `app/routers/jti/chat.py`, `app/routers/hciot/chat.py`
- Modify: `app/services/jti/main_agent.py`, `app/services/hciot/main_agent.py`, `app/services/jti/response_assembly.py`
- Modify TTS tests/support imports

1. Add failing tests for `make_tts_job_manager`, first-character environment parsing, cache identity, and JTI/HCIoT config values.
2. Confirm the tests fail because the General factory does not exist.
3. Implement cached `get_tts_job_manager(app, env_var, default_char)` and use shared `prepare_tts_text` directly.
4. Remove app-specific TTS modules and run TTS, JTI response assembly, and HCIoT API tests.

### Task 3: Make JTI main agent an injected General-layer runtime

**Files:**
- Create: `app/services/general/managed_agent.py`
- Modify: `app/services/jti/main_agent.py`
- Test: `tests/general/test_jti_general_migration.py`

1. Add a failing test requiring the JTI agent to be an instance of the General managed-agent base with JTI configuration injected.
2. Extract the fixed-app `BaseAgent` hooks into `ManagedAppAgent` and a configuration dataclass.
3. Reduce `app/services/jti/main_agent.py` to JTI RAG declaration/configuration and singleton wiring.
4. Run JTI agent, prompt, response assembly, and General RAG routing tests.

### Task 4: Move JTI chat and quiz orchestration behind General services

**Files:**
- Create: `app/services/general/managed_chat.py`
- Create: `app/services/general/managed_quiz.py`
- Modify: `app/routers/jti/chat.py`
- Modify: `app/routers/jti/quiz.py`
- Test: `tests/general/test_jti_general_migration.py`

1. Snapshot JTI route methods, paths, and response models in a failing contract test that also requires router handlers to delegate to General services.
2. Move session creation/message orchestration into an injected `ManagedChatService`; keep history endpoints and their persistence unchanged.
3. Move explicit quiz start/pause orchestration into `ManagedQuizService` using the shared quiz runtime/config.
4. Keep JTI router functions as thin request/response adapters and run route-contract, quiz, history, and TTS tests.

### Task 5: Reuse General prompt and quiz-bank mechanisms

**Files:**
- Modify: `app/routers/jti/prompts.py`
- Refactor: `app/routers/general/quiz_bank.py`
- Replace: `app/routers/jti/quiz_bank.py` with a fixed-store adapter/factory output
- Test: `tests/general/test_jti_general_migration.py`

1. Add route-contract tests for every JTI prompt and quiz-bank method/path plus fixed store isolation.
2. Keep the existing shared persona router factory, but source its service/config wiring from General managed-app configuration.
3. Extract a quiz-bank router factory/service used by General dynamic stores and the fixed JTI stores.
4. Verify all JTI public/admin aliases and schemas are unchanged.

### Task 6: Remove obsolete JTI service duplication and verify

**Files:**
- Remove only JTI implementation modules superseded by Tasks 1-5.
- Preserve: `app/routers/jti/*` compatibility shells, `app/routers/jti/knowledge.py`, migration scripts, JTI prompt/config data needed for injected behavior.

1. Assert no production General module imports JTI runtime implementations.
2. Run `git diff --check` and Python compilation.
3. Run targeted JTI, General quiz/chat/prompt/quiz-bank, HCIoT TTS, and route-contract tests independently.
4. Run the full pytest suite and separate pre-existing baseline failures from new failures.
5. Report the unstaged diff; do not mark this plan or the design spec Done without explicit user confirmation.
