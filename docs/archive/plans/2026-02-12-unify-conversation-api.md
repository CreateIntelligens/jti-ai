# Unify Conversation API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify JTI and General chat API structure so both use `/conversations` as the top-level resource, eliminating redundant `/sessions` and `/session/{id}` endpoints.

**Architecture:** Remove three admin-only JTI session endpoints (`GET /sessions`, `GET /session/{id}`, `DELETE /session/{id}`) that the frontend doesn't use. Ensure `DELETE /conversations/{session_id}` behaves identically in both modes. All response models already exist as Pydantic schemas — no new models needed.

**Tech Stack:** FastAPI, Pydantic, Python

---

## Pre-Implementation Findings

### Frontend Usage (confirmed no usage of session endpoints)
- `frontend/src/` has **zero** references to `/api/jti/sessions` or `/api/jti/session/`
- Frontend only uses: `/api/jti/chat/start`, `/api/jti/chat/message`, `/api/jti/conversations`, `/api/jti/conversations/export`
- **Safe to remove all three session endpoints.**

### Current Pydantic Models (all in `app/routers/jti.py`)
These models already exist and are already used as `response_model` on the conversation endpoints:
- `DeleteConversationResponse` — used by both JTI and General DELETE
- `ConversationsBySessionResponse` / `ConversationsGroupedResponse` — used by JTI GET /conversations
- `GeneralConversationsResponse` — used by General GET /conversations
- `ExportConversationsResponse` / `ExportGeneralConversationsResponse` — used by exports

**All conversation endpoints already have response_model declared.** No work needed for task 3 in the spec.

### DELETE Behavior Gap
- **General** (`app/main.py:424`): deletes logs + session + cleans `user_managers[session_id]`
- **JTI** (`app/routers/jti.py:904`): deletes logs + session, but does **NOT** clean any in-memory manager
- JTI has no equivalent of `user_managers` dict — its state is fully managed by `session_manager`. So the only real gap is that JTI doesn't call any in-memory cleanup, but that's because there's nothing to clean up. The behavior is already effectively equivalent.

---

## Tasks

### Task 1: Remove JTI Session Endpoints

**Files:**
- Modify: `app/routers/jti.py` (lines 820-852)

**Step 1: Remove the three session-only endpoints**

Remove these three route handlers from `app/routers/jti.py`:

1. `DELETE /session/{session_id}` (lines 820-836) — `delete_session()`
2. `GET /sessions` (lines 839-852) — `list_sessions()`
3. `GET /session/{session_id}` (lines 186-207) — `get_session()` 

Also remove the `GetSessionResponse` model (lines 70-72) since it's only used by `get_session()`.

**Step 2: Run existing tests to verify nothing breaks**

Run: `cd /home/human/jtai && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass (no test references these admin-only endpoints)

**Step 3: Verify frontend still works by grep**

Run: `grep -rn "GetSessionResponse\|/session/" app/routers/jti.py`
Expected: No matches (confirming clean removal)

**Step 4: Commit**

```bash
git add app/routers/jti.py
git commit -m "refactor: remove redundant JTI session endpoints

Remove GET /sessions, GET /session/{id}, and DELETE /session/{id}.
Frontend doesn't use these — confirmed by searching frontend/src/.
Conversation management is unified under /conversations endpoints."
```

---

### Task 2: Verify DELETE Behavior Consistency

**Files:**
- Review: `app/routers/jti.py` (lines 904-920)
- Review: `app/main.py` (lines 424-448)

**Step 1: Confirm no in-memory manager cleanup needed for JTI**

JTI's DELETE `/conversations/{session_id}` already:
- ✅ Deletes conversation logs via `conversation_logger.delete_session_logs()`
- ✅ Deletes session via `session_manager.delete_session()`

General's DELETE `/conversations/{session_id}` does the same plus:
- ✅ Cleans `user_managers[session_id]` (FileSearchManager instances)

JTI has no equivalent in-memory dict, so no code change is needed. The behavior is already consistent for each mode's context.

**Step 2: Run full test suite to confirm baseline**

Run: `cd /home/human/jtai && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass

**Step 3: Commit (documentation-only if no code change)**

No code change needed — this task is verification only. If the analysis above is confirmed during implementation, skip the commit.

---

## Summary of Changes

| What | Action |
|------|--------|
| `GET /api/jti/sessions` | **Remove** (admin-only, no frontend usage) |
| `GET /api/jti/session/{id}` | **Remove** (admin-only, no frontend usage) |
| `DELETE /api/jti/session/{id}` | **Remove** (redundant with DELETE /conversations/{id}) |
| `GetSessionResponse` model | **Remove** (only used by removed endpoint) |
| DELETE behavior | **No change needed** (already consistent) |
| Response models | **No change needed** (already declared on all endpoints) |

## Final Unified API

After this change, both modes will have identical API shapes:

| Operation | JTI | General |
|-----------|-----|---------|
| List history | `GET /api/jti/conversations` | `GET /api/chat/conversations` |
| Export | `GET /api/jti/conversations/export` | `GET /api/chat/conversations/export` |
| Delete | `DELETE /api/jti/conversations/{session_id}` | `DELETE /api/chat/conversations/{session_id}` |
