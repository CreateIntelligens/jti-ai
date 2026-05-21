# JTI Quiz Integration Scripts

This directory contains shell scripts that were originally used for manual end-to-end checks of the JTI quiz flow.

## Current Status

These scripts are **legacy/manual smoke-test helpers**, not part of the normal automated test suite. The maintained regression coverage is in the Python tests under `tests/jti/`, `tests/quiz/`, and route-level tests.

The scripts need modernization before they can be treated as reliable current checks:

- They default to `http://localhost:8913/api/jti`, while Docker Compose currently defaults to port `8008`.
- They call old endpoints such as `/session/new` and `/chat`; the current runtime endpoints are `/chat/start` and `/chat/message`.
- `test_quiz_api.sh` references `/quiz/resume`, but the current JTI quiz router exposes `/quiz/start` and `/quiz/pause` only.
- Current runtime routes use bearer/API-key auth through `verify_auth`, so ad-hoc curl commands need the proper auth header for the target environment.

## Scripts

- `test_quiz_flow.sh`: old conversation-driven quiz flow smoke test.
- `test_quiz_api.sh`: old direct quiz API smoke test.

## Recommended Checks

Use the maintained test suite for normal verification:

```bash
pytest tests/jti tests/quiz
```

For frontend-related quiz or app behavior, use the frontend test runner from `frontend/`:

```bash
pnpm test
```

If these shell scripts are revived, update the endpoints, auth headers, and expected response shapes before using them for release validation.
