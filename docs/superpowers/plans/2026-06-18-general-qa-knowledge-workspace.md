# General QA Knowledge Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring HCIoT's topic-based QA knowledge workspace (upload + QA/CSV editing + topic "quick-question" buttons + reindex + images) to general dynamic stores, isolated per `store_name`.

**Architecture:** The shared QA-KB stack (`app/services/_shared/qa_kb/*`, `app/routers/_shared/qa_kb_router.py`) partitions data purely by a single `language` string. General's existing convention already puts `store_name` in that slot (see `sync_to_rag(GENERAL_NAMESPACE, store_name, ...)`). So we add **new `NAMESPACE="general"` store subclasses** (knowledge/topic/image, the image store gaining a real `store_name` dimension), mount the **existing shared QA-KB router** under `/api/general-admin/stores/{store_name}/knowledge` with general store factories, add **general topics + images routers** keyed by `store_name`, and add a thin **frontend `GeneralKnowledgeWorkspace`** wrapper + general API client. No risky refactor of the shared base.

**Tech Stack:** FastAPI, MongoDB (pymongo), React + TypeScript (Vite), pytest. Backend file ops inside the container (`docker compose ... backend`). Frontend uses `pnpm`.

## Global Constraints

- 一律參考 HCIoT 既有實作；行為/驗證/UI 對齊 HCIoT，唯一差異是多一個 `store_name` 維度。
- topic 分隔：每個 general store 獨立 topics，以 `store_name` keying，語言固定 `"zh"`，不分 zh/en。
- AI QA 抽取關閉：`disableAiQaExtraction: true` 前端、`include_extract=False` 後端；不建立 general 的 `qa_extract` 端點。
- 「正確 CSV 格式才進塊速問答」由共用 `qa_kb` 既有邏輯自動繼承，不另寫驗證。
- RAG 隔離：general doc 在 LanceDB 必須帶 `store_name`（沿用既有 general 上傳把 store_name 放在 sync_to_rag 的 language 參數位的慣例）。
- 不破壞 HCIoT/JTI：新增 `NAMESPACE="general"` 子類別，完全不改共用 base 既有行為。
- 不收斂 general 既有「舊單檔上傳」(`app/services/knowledge_store.py`)；短期並存。
- 前端禁用新增 `px`，用 rem/%/vh；commit message 用單行 conventional subject；繁體中文。
- 所有 docker / file 操作在容器內;在 worktree `/home/human/jtai/.worktrees/jtai-rag` 操作,容器名前綴跟目錄(`jtai-rag-backend-1`)。

---

## File Structure

**Backend — new:**
- `app/services/general/knowledge_store.py` — `GeneralKnowledgeStore(QaKbKnowledgeStoreBase)`, `NAMESPACE="general"`.
- `app/services/general/topic_store.py` — `GeneralTopicStore(TopicStoreBase)`, own collections, language slot = store_name.
- `app/services/general/image_store.py` — `GeneralImageStore`, `hciot_images`-style but with `store_name` key.
- `app/routers/general/knowledge.py` — builds shared `build_qa_kb_router` with general factories; mounted per store_name.
- `app/routers/general/topics_admin.py` — per-store topic CRUD (single-language, plain labels).
- `app/routers/general/images.py` — per-store image serve/upload/delete.

**Backend — modify:**
- `app/main.py` — register the three new general routers.
- `app/services/rag/backfill.py` — ensure general topic CSV sync keys by store_name (verify, likely already correct).

**Frontend — new:**
- `frontend/src/components/general/GeneralKnowledgeWorkspace.tsx` — thin wrapper over `QaKnowledgeWorkspace`.

**Frontend — modify:**
- `frontend/src/services/api/general.ts` — add per-store QA-KB API functions.
- `frontend/src/App.tsx` — mount workspace + admin-gated entry, pass `currentStore` as store_name.

**Tests — new:**
- `tests/services/general/test_general_knowledge_store.py`
- `tests/services/general/test_general_topic_store.py`
- `tests/services/general/test_general_image_store.py`
- `tests/routers/general/test_general_knowledge_router.py`
- `tests/routers/general/test_general_topics_images.py`

---

## Task 1: GeneralKnowledgeStore (per-store knowledge files)

**Files:**
- Create: `app/services/general/knowledge_store.py`
- Test: `tests/services/general/test_general_knowledge_store.py`

**Interfaces:**
- Consumes: `app.services._shared.qa_kb.knowledge_store_base.QaKbKnowledgeStoreBase` (provides `list_files(language)`, `insert_file(language, filename, data, ...)`, `get_file(language, filename)`, `delete_file(language, filename)`, etc., all keyed by `self.NAMESPACE` + the `language` arg).
- Produces: `get_general_knowledge_store() -> GeneralKnowledgeStore`. Callers pass `store_name` in the `language` parameter slot for per-store isolation.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/general/test_general_knowledge_store.py
from app.services.general.knowledge_store import get_general_knowledge_store


def test_files_isolated_by_store_name():
    store = get_general_knowledge_store()
    store.insert_file("store-a", "faq.csv", b"q,a\nhi,hello\n", content_type="text/csv")
    store.insert_file("store-b", "faq.csv", b"q,a\nbye,goodbye\n", content_type="text/csv")

    a_files = [f["filename"] for f in store.list_files("store-a")]
    b_files = [f["filename"] for f in store.list_files("store-b")]

    assert "faq.csv" in a_files
    assert "faq.csv" in b_files
    a_doc = store.get_file("store-a", "faq.csv")
    assert b"hi,hello" in a_doc["data"]
    # cleanup
    store.delete_file("store-a", "faq.csv")
    store.delete_file("store-b", "faq.csv")
```

- [ ] **Step 2: Run test to verify it fails**

Run (inside container): `docker compose exec backend pytest tests/services/general/test_general_knowledge_store.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.general.knowledge_store`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/general/knowledge_store.py
"""General per-store knowledge file storage — thin subclass of the shared qa_kb base.

The `language` argument on the base methods carries the general ``store_name``
(general's established RAG-keying convention), giving per-store isolation for free.
"""

from __future__ import annotations

from app.services._shared.qa_kb.knowledge_store_base import QaKbKnowledgeStoreBase


class GeneralKnowledgeStore(QaKbKnowledgeStoreBase):
    DB_NAME = "general_app"
    COLLECTION_NAME = "general_knowledge_files"
    NAMESPACE = "general"


_knowledge_store: GeneralKnowledgeStore | None = None


def get_general_knowledge_store() -> GeneralKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = GeneralKnowledgeStore()
    return _knowledge_store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/services/general/test_general_knowledge_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/general/knowledge_store.py tests/services/general/test_general_knowledge_store.py
git commit -m "feat: add per-store general knowledge file store"
```

---

## Task 2: GeneralTopicStore (per-store topics)

**Files:**
- Create: `app/services/general/topic_store.py`
- Test: `tests/services/general/test_general_topic_store.py`

**Interfaces:**
- Consumes: `app.services._shared.qa_kb.topic_store_base.TopicStoreBase` (constructor `__init__(self, language)` sets `self.language`; all queries go through `_language_query() -> {"language": self.language}`; methods: `list_topics()`, `get_topic(topic_id)`, `upsert_topic(topic_id, data)`, `update_topic(topic_id, data)`, `delete_topic(topic_id)`, `delete_topics(ids)`, `reorder_topics(ids)`, `list_categories()`).
- Produces: `get_general_topic_store(store_name: str) -> GeneralTopicStore`. The `store_name` is passed as the base's `language`, so topics are isolated per store. No bilingual partitioning.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/general/test_general_topic_store.py
from app.services.general.topic_store import get_general_topic_store


def test_topics_isolated_by_store_name():
    a = get_general_topic_store("store-a")
    b = get_general_topic_store("store-b")
    a.upsert_topic("greetings", {"labels": "Greetings", "questions": ["hi"]})

    a_ids = [t["topic_id"] for t in a.list_topics()]
    b_ids = [t["topic_id"] for t in b.list_topics()]
    assert "greetings" in a_ids
    assert "greetings" not in b_ids
    # cleanup
    a.delete_topic("greetings")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/services/general/test_general_topic_store.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/general/topic_store.py
"""General per-store topic storage — thin subclass of the shared topic base.

The base partitions purely by ``self.language``; general passes ``store_name``
there, so each store gets its own isolated topic set. General is single-language.
"""

from __future__ import annotations

from app.services._shared.qa_kb.topic_store_base import TopicStoreBase


class GeneralTopicStore(TopicStoreBase):
    DB_NAME = "general_app"
    COLLECTION_NAME = "general_topics"
    CATEGORY_COLLECTION_NAME = "general_categories"
    NAMESPACE = "general"


def get_general_topic_store(store_name: str) -> GeneralTopicStore:
    """Return a topic store scoped to one general store. Not cached across
    store_names because the partition key (store_name) is the constructor arg."""
    return GeneralTopicStore(store_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/services/general/test_general_topic_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/general/topic_store.py tests/services/general/test_general_topic_store.py
git commit -m "feat: add per-store general topic store"
```

---

## Task 3: GeneralImageStore (per-store images)

**Files:**
- Create: `app/services/general/image_store.py`
- Test: `tests/services/general/test_general_image_store.py`

**Interfaces:**
- Consumes: `app.services.mongo_client.get_mongo_db`.
- Produces: `get_general_image_store() -> GeneralImageStore` with methods keyed by `store_name`:
  - `get_image(store_name: str, image_id: str) -> dict | None`
  - `list_images(store_name: str) -> list[dict]` (each item: `{"image_id", "content_type", "size", "url"}`, url = `/api/general/stores/{store_name}/images/{image_id}`)
  - `upsert_image(store_name: str, image_id: str, data: bytes, content_type: str) -> None`
  - `image_exists(store_name: str, image_id: str) -> bool`
  - `delete_image(store_name: str, image_id: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/services/general/test_general_image_store.py
from app.services.general.image_store import get_general_image_store


def test_images_isolated_by_store_name():
    store = get_general_image_store()
    store.upsert_image("store-a", "logo", b"\x89PNG", "image/png")

    assert store.image_exists("store-a", "logo")
    assert not store.image_exists("store-b", "logo")
    ids = [i["image_id"] for i in store.list_images("store-a")]
    assert "logo" in ids
    assert store.list_images("store-b") == []
    # cleanup
    store.delete_image("store-a", "logo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/services/general/test_general_image_store.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/general/image_store.py
"""General per-store image storage in MongoDB (store_name-scoped)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson.binary import Binary
from pymongo import ASCENDING

from app.services.mongo_client import get_mongo_db


class GeneralImageStore:
    COLLECTION_NAME = "general_images"

    def __init__(self):
        self.db = get_mongo_db("general_app")
        self.collection = self.db[self.COLLECTION_NAME]
        # Compound unique key: one image_id per store.
        self.collection.create_index(
            [("store_name", ASCENDING), ("image_id", ASCENDING)], unique=True
        )

    @staticmethod
    def _to_bytes(data: Any) -> bytes:
        if isinstance(data, (bytes, bytearray, Binary)):
            return bytes(data)
        return b""

    def get_image(self, store_name: str, image_id: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"store_name": store_name, "image_id": image_id})
        if not doc:
            return None
        doc["data"] = self._to_bytes(doc.get("data"))
        return doc

    def list_images(self, store_name: str) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            {"store_name": store_name},
            {"_id": 0, "image_id": 1, "content_type": 1, "size": 1},
        ).sort("image_id", 1)
        return [
            {
                "image_id": doc["image_id"],
                "content_type": doc.get("content_type"),
                "size": doc.get("size"),
                "url": f"/api/general/stores/{store_name}/images/{doc['image_id']}",
            }
            for doc in cursor
        ]

    def upsert_image(
        self, store_name: str, image_id: str, data: bytes, content_type: str
    ) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"store_name": store_name, "image_id": image_id},
            {
                "$set": {
                    "store_name": store_name,
                    "image_id": image_id,
                    "data": Binary(data),
                    "content_type": content_type,
                    "size": len(data),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def image_exists(self, store_name: str, image_id: str) -> bool:
        return (
            self.collection.count_documents(
                {"store_name": store_name, "image_id": image_id}, limit=1
            )
            > 0
        )

    def delete_image(self, store_name: str, image_id: str) -> bool:
        result = self.collection.delete_one(
            {"store_name": store_name, "image_id": image_id}
        )
        return result.deleted_count > 0


_image_store: GeneralImageStore | None = None


def get_general_image_store() -> GeneralImageStore:
    global _image_store
    if _image_store is None:
        _image_store = GeneralImageStore()
    return _image_store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/services/general/test_general_image_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/general/image_store.py tests/services/general/test_general_image_store.py
git commit -m "feat: add per-store general image store"
```

---

## Task 4: General knowledge router (shared QA-KB router with general factories)

**Files:**
- Create: `app/routers/general/knowledge.py`
- Modify: `app/main.py` (register router)
- Test: `tests/routers/general/test_general_knowledge_router.py`

**Interfaces:**
- Consumes:
  - `app.routers._shared.qa_kb_router.build_qa_kb_router(config, *, include_knowledge: bool, include_extract: bool) -> APIRouter` and `QaKbRouterConfig(tag, app, knowledge_store_factory, topic_store_factory, rag_source_type, invalidate_cache, other_language)`.
  - `get_general_knowledge_store()` (Task 1), `get_general_topic_store(store_name)` (Task 2).
  - Pattern reference: `app/routers/hciot/knowledge.py`.
- Produces: `router: APIRouter`. The shared router's endpoints use `language: str = "zh"` as the partition key. For general, the **store_name is passed as `language`** by the frontend, so no router signature change is needed. Mounted at `/api/general-admin/stores/{store_name}/knowledge` is NOT possible directly (shared router has no `{store_name}` path segment); instead mount at `/api/general-admin/knowledge` and the client passes `?language=<store_name>`. Reindex/cache invalidation keyed by `rag_source_type="general"`.

> NOTE: The shared router keys everything by the `language` query/form field. General reuses that field to carry `store_name`. This matches `app/routers/general/stores.py` which already calls `sync_to_rag(GENERAL_NAMESPACE, store_name, ...)` (store_name in the language slot).

- [ ] **Step 1: Write the failing test**

```python
# tests/routers/general/test_general_knowledge_router.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ADMIN = {"Authorization": "Bearer test-admin-key"}  # see conftest for admin key fixture


def test_general_upload_list_delete_roundtrip():
    csv = ("q,a\nHello,Hi there\n").encode()
    r = client.post(
        "/api/general-admin/knowledge/upload/",
        params={"language": "store-x"},
        files={"file": ("faq.csv", csv, "text/csv")},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/general-admin/knowledge/files/", params={"language": "store-x"}, headers=ADMIN)
    assert r.status_code == 200
    names = [f["filename"] for f in r.json()["files"]]
    assert "faq.csv" in names

    # isolation: another store does not see it
    r2 = client.get("/api/general-admin/knowledge/files/", params={"language": "store-y"}, headers=ADMIN)
    assert "faq.csv" not in [f["filename"] for f in r2.json()["files"]]

    client.delete("/api/general-admin/knowledge/files/faq.csv", params={"language": "store-x"}, headers=ADMIN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/routers/general/test_general_knowledge_router.py -v`
Expected: FAIL (404 — route not registered).

- [ ] **Step 3: Write minimal implementation**

```python
# app/routers/general/knowledge.py
"""General per-store knowledge router — thin wrapper over the shared qa_kb router.

Reuses build_qa_kb_router; the shared router keys data by its ``language`` field,
which general repurposes to carry ``store_name`` (general's RAG-keying convention).
AI Q&A extraction is disabled (include_extract=False).
"""

from __future__ import annotations

from app.routers._shared.qa_kb_router import QaKbRouterConfig, build_qa_kb_router
from app.services.general.knowledge_store import get_general_knowledge_store
from app.services.general.topic_store import get_general_topic_store


def _invalidate_cache(_store_name: str | None) -> None:
    # General chat resolves RAG per request; no module-level cache to bust.
    return None


def _other_language(_store_name: str) -> str:
    # General is single-language; "other language" is itself (no-op partner).
    return _store_name


def _make_config() -> QaKbRouterConfig:
    return QaKbRouterConfig(
        tag="General Knowledge",
        app="general",
        knowledge_store_factory=lambda: get_general_knowledge_store(),
        topic_store_factory=lambda store_name: get_general_topic_store(store_name or ""),
        rag_source_type="general",
        invalidate_cache=_invalidate_cache,
        other_language=_other_language,
    )


router = build_qa_kb_router(_make_config(), include_knowledge=True, include_extract=False)
```

Then in `app/main.py`, next to the hciot knowledge registration (after line ~471), add:

```python
from .routers.general import knowledge as general_knowledge  # with other general imports near top

app.include_router(general_knowledge.router, prefix="/api/general-admin/knowledge")
app.include_router(general_knowledge.router, prefix="/api/general/knowledge", include_in_schema=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/routers/general/test_general_knowledge_router.py -v`
Expected: PASS. Then verify HCIoT/JTI still green: `docker compose exec backend pytest tests/routers -q`.

- [ ] **Step 5: Commit**

```bash
git add app/routers/general/knowledge.py app/main.py tests/routers/general/test_general_knowledge_router.py
git commit -m "feat: mount per-store general knowledge router"
```

---

## Task 5: General topics + images routers

**Files:**
- Create: `app/routers/general/topics_admin.py`, `app/routers/general/images.py`
- Modify: `app/main.py`
- Test: `tests/routers/general/test_general_topics_images.py`

**Interfaces:**
- Consumes: `get_general_topic_store(store_name)` (Task 2), `get_general_image_store()` (Task 3), `app.auth.require_kb_access("general")`.
- Produces routers mounted at:
  - topics admin: `/api/general-admin/stores/{store_name}/topics` (GET list, POST create, PUT `/reorder`, POST `/delete-batch`, PUT `/{topic_id}`, DELETE `/{topic_id}`)
  - topics public: `/api/general/stores/{store_name}/topics` (GET list of visible topics for quick-question buttons)
  - images: `/api/general/stores/{store_name}/images/{image_id}` (GET), admin upload/delete/list under `/api/general-admin/stores/{store_name}/images`.

- [ ] **Step 1: Write the failing test**

```python
# tests/routers/general/test_general_topics_images.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ADMIN = {"Authorization": "Bearer test-admin-key"}


def test_general_topic_crud_isolated():
    r = client.post(
        "/api/general-admin/stores/store-t/topics/",
        json={"id": "greet", "label": "Greetings", "questions": ["hi"]},
        headers=ADMIN,
    )
    assert r.status_code in (200, 201), r.text

    r = client.get("/api/general/stores/store-t/topics", headers=ADMIN)
    assert "greet" in [t["id"] for t in r.json()]
    r2 = client.get("/api/general/stores/store-u/topics", headers=ADMIN)
    assert "greet" not in [t["id"] for t in r2.json()]

    client.delete("/api/general-admin/stores/store-t/topics/greet", headers=ADMIN)


def test_general_image_upload_get_delete():
    r = client.post(
        "/api/general-admin/stores/store-i/images",
        files={"file": ("logo.png", b"\x89PNG\r\n", "image/png")},
        data={"image_id": "logo"},
        headers=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    r = client.get("/api/general/stores/store-i/images/logo", headers=ADMIN)
    assert r.status_code == 200
    client.delete("/api/general-admin/stores/store-i/images/logo", headers=ADMIN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/routers/general/test_general_topics_images.py -v`
Expected: FAIL (404).

- [ ] **Step 3: Write minimal implementation**

```python
# app/routers/general/topics_admin.py
"""General per-store topics API (single-language, plain labels)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_kb_access
from app.services.general.topic_store import get_general_topic_store

router = APIRouter(tags=["General Topics"], dependencies=[Depends(require_kb_access("general"))])
public_router = APIRouter(tags=["General Topics"])


class CreateTopicRequest(BaseModel):
    id: str
    label: str
    questions: list[str] = []


class UpdateTopicRequest(BaseModel):
    label: str | None = None
    questions: list[str] | None = None
    hidden_questions: list[str] | None = None


class ReorderTopicsRequest(BaseModel):
    topic_ids: list[str]


class DeleteTopicsRequest(BaseModel):
    topic_ids: list[str]


def _public_topic(topic: dict) -> dict:
    return {
        "id": topic.get("topic_id", ""),
        "label": topic.get("labels", ""),
        "order": topic.get("order"),
        "questions": [
            q for q in (topic.get("questions") or [])
            if q not in (topic.get("hidden_questions") or [])
        ],
    }


@public_router.get("/stores/{store_name}/topics")
def list_public_topics(store_name: str):
    store = get_general_topic_store(store_name)
    return [_public_topic(t) for t in store.list_topics()]


@router.post("/stores/{store_name}/topics/", status_code=201)
def create_topic(store_name: str, request: CreateTopicRequest):
    store = get_general_topic_store(store_name)
    store.upsert_topic(request.id, {"labels": request.label, "questions": request.questions})
    return {"ok": True, "id": request.id}


@router.put("/stores/{store_name}/topics/reorder")
def reorder_topics(store_name: str, request: ReorderTopicsRequest):
    store = get_general_topic_store(store_name)
    return {"updated": store.reorder_topics(request.topic_ids)}


@router.post("/stores/{store_name}/topics/delete-batch")
def delete_topics(store_name: str, request: DeleteTopicsRequest):
    store = get_general_topic_store(store_name)
    return {"deleted": store.delete_topics(request.topic_ids)}


@router.put("/stores/{store_name}/topics/{topic_id:path}")
def update_topic(store_name: str, topic_id: str, request: UpdateTopicRequest):
    store = get_general_topic_store(store_name)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    if "label" in data:
        data["labels"] = data.pop("label")
    if not store.update_topic(topic_id, data):
        raise HTTPException(status_code=404, detail="topic not found")
    return {"ok": True}


@router.delete("/stores/{store_name}/topics/{topic_id:path}")
def delete_topic(store_name: str, topic_id: str):
    store = get_general_topic_store(store_name)
    if not store.delete_topic(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    return {"ok": True}
```

```python
# app/routers/general/images.py
"""General per-store image serving from MongoDB."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth import require_kb_access
from app.services.general.image_store import get_general_image_store

MAX_IMAGE_SIZE = 10 * 1024 * 1024

router = APIRouter(tags=["General Images"])
admin_router = APIRouter(
    tags=["General Admin Images"], dependencies=[Depends(require_kb_access("general"))]
)


@router.get("/stores/{store_name}/images/{image_id}")
def get_image(store_name: str, image_id: str):
    doc = get_general_image_store().get_image(store_name, image_id)
    if not doc:
        raise HTTPException(status_code=404, detail="image not found")
    return Response(content=doc["data"], media_type=doc.get("content_type") or "image/png")


@admin_router.get("/stores/{store_name}/images")
def list_images(store_name: str):
    return {"images": get_general_image_store().list_images(store_name)}


@admin_router.post("/stores/{store_name}/images", status_code=status.HTTP_201_CREATED)
async def upload_image(store_name: str, image_id: str = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="image too large")
    get_general_image_store().upsert_image(
        store_name, image_id, data, file.content_type or "image/png"
    )
    return {"image_id": image_id, "url": f"/api/general/stores/{store_name}/images/{image_id}"}


@admin_router.delete("/stores/{store_name}/images/{image_id}")
def delete_image(store_name: str, image_id: str):
    if not get_general_image_store().delete_image(store_name, image_id):
        raise HTTPException(status_code=404, detail="image not found")
    return {"ok": True}
```

In `app/main.py` (after Task 4 general knowledge registration), add:

```python
from .routers.general import topics_admin as general_topics, images as general_images

app.include_router(general_topics.public_router, prefix="/api/general")
app.include_router(general_topics.router, prefix="/api/general-admin")
app.include_router(general_images.router, prefix="/api/general")
app.include_router(general_images.admin_router, prefix="/api/general-admin")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/routers/general/test_general_topics_images.py -v`
Expected: PASS. Regression: `docker compose exec backend pytest tests/routers -q`.

- [ ] **Step 5: Commit**

```bash
git add app/routers/general/topics_admin.py app/routers/general/images.py app/main.py tests/routers/general/test_general_topics_images.py
git commit -m "feat: add per-store general topics and images routers"
```

---

## Task 6: Verify RAG sync isolates general by store_name

**Files:**
- Modify (if needed): `app/services/rag/backfill.py`
- Test: extend `tests/routers/general/test_general_knowledge_router.py`

**Interfaces:**
- Consumes: existing `sync_to_rag(source_type, language, filename, file_bytes)` and the general backfill path. For general, `source_type="general"`, `language=store_name`.
- Produces: confirmation that a chunk uploaded to `store-x` is retrievable only when querying with `store_name="store-x"`.

- [ ] **Step 1: Write the failing/characterization test**

```python
def test_general_chunks_keyed_by_store_name():
    # Upload to store-x, then assert backfill wrote chunks under store_name="store-x".
    from app.services.rag import backfill as bf
    csv = b"q,a\nWhat is X,X is a thing\n"
    client.post(
        "/api/general-admin/knowledge/upload/",
        params={"language": "store-x"},
        files={"file": ("x.csv", csv, "text/csv")},
        headers=ADMIN,
    )
    svc = bf.BackfillService()
    # Inspect LanceDB rows for this store; the exact accessor mirrors how hciot
    # retrieval filters. Assert at least one row carries store_name/language == "store-x"
    # and none leak to "store-y".
    # (Implement using the same query path retrieval uses for general.)
    rows_x = svc.lancedb_store  # placeholder accessor — use the real retrieval filter
    assert rows_x is not None
    client.delete("/api/general-admin/knowledge/files/x.csv", params={"language": "store-x"}, headers=ADMIN)
```

- [ ] **Step 2: Run and inspect actual backfill keying**

Run: `docker compose exec backend pytest "tests/routers/general/test_general_knowledge_router.py::test_general_chunks_keyed_by_store_name" -v`
Read `app/services/rag/backfill.py` general branch: confirm the LanceDB write tags rows with `language=store_name` (the value passed through). If general retrieval already filters by that field, no code change is needed — turn the test into a real assertion against the retrieval filter. If chunks are NOT store-scoped, add `store_name` to the general write + retrieval filter.

- [ ] **Step 3: Implement fix only if isolation is missing**

If the inspection shows general chunks are not isolated, thread `store_name` into the general LanceDB write and the general retrieval `where` clause in `backfill.py` / the general retrieval path. (No code shown here because the change is conditional on Step 2's finding; implement to make the isolation assertion pass.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/routers/general/test_general_knowledge_router.py -v`
Expected: PASS — `store-x` chunk present, no leak to `store-y`.

- [ ] **Step 5: Commit**

```bash
git add app/services/rag/backfill.py tests/routers/general/test_general_knowledge_router.py
git commit -m "test: verify general RAG chunks are isolated per store_name"
```

---

## Task 7: Frontend general API client functions

**Files:**
- Modify: `frontend/src/services/api/general.ts`
- Test: covered via the workspace mount in Task 8 (manual + existing workspace tests). No new unit test file (matches existing api client convention of no isolated unit tests).

**Interfaces:**
- Consumes: existing `base.ts` request helpers used elsewhere in `general.ts` (follow the existing `uploadStoreFile` / `fetchFiles` style for headers/error handling).
- Produces (exact names, all take `storeName` and pass it as the `language` field; mirror the `QaWorkspaceApiClient` interface in `frontend/src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace.tsx`):
  - `listGeneralKnowledgeFiles(storeName: string)`
  - `listGeneralTopicsAdmin(storeName: string)`
  - `listGeneralImages(storeName: string)`
  - `getGeneralKnowledgeFileContent(filename, storeName)`
  - `uploadGeneralKnowledgeFileWithTopic(opts)`
  - `deleteGeneralKnowledgeFile(filename, storeName)`
  - `updateGeneralTopic`, `reorderGeneralTopics`, `setGeneralCategoryHidden`, `createGeneralTopic`
  - `uploadGeneralImage`, `deleteGeneralImage`, `deleteUnusedGeneralImages`
  - `updateGeneralKnowledgeFileMetadata`, `updateGeneralKnowledgeFileContent`, `downloadGeneralKnowledgeFile`
  - `getGeneralTopicMergedCsv`, `saveGeneralTopicMergedCsv`
  - `parseQaCsvText` (reuse existing shared one if present)

- [ ] **Step 1: Add the API functions**

Append to `frontend/src/services/api/general.ts`, following the existing request helper style. Each maps to the Task 4/5 routes, passing `storeName` as the `language` query/form field for knowledge endpoints and as the `{store_name}` path segment for topics/images. Example (knowledge list):

```ts
// general.ts — append
const GENERAL_KB = '/api/general-admin/knowledge';

export async function listGeneralKnowledgeFiles(storeName: string) {
  return request<{ files: HciotKnowledgeFile[] }>(
    `${GENERAL_KB}/files/?language=${encodeURIComponent(storeName)}`,
  );
}

export async function uploadGeneralKnowledgeFileWithTopic(opts: {
  storeName: string; file: File; categoryId?: string; topicId?: string;
  categoryLabel?: string; topicLabel?: string; hiddenQuestions?: string[];
}) {
  const form = new FormData();
  form.append('file', opts.file);
  form.append('language', opts.storeName);
  if (opts.topicId) form.append('topic_id', opts.topicId);
  if (opts.categoryId) form.append('category_id', opts.categoryId);
  if (opts.categoryLabel) form.append('category_label', opts.categoryLabel);
  if (opts.topicLabel) form.append('topic_label', opts.topicLabel);
  if (opts.hiddenQuestions) form.append('hidden_questions', JSON.stringify(opts.hiddenQuestions));
  return requestForm(`${GENERAL_KB}/upload/`, form);
}
```

Implement the remaining functions in the same pattern (topics → `/api/general-admin/stores/${storeName}/topics...`, images → `/api/general-admin/stores/${storeName}/images`). Reuse `reindexRag('general')` / `getReindexStatus('general')` already exported (extend `RagSourceType` to include `'general'` in `general.ts` if not present).

- [ ] **Step 2: Type-check**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: no new errors in `general.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api/general.ts
git commit -m "feat: add general per-store QA knowledge API client functions"
```

---

## Task 8: Frontend GeneralKnowledgeWorkspace + mount in App

**Files:**
- Create: `frontend/src/components/general/GeneralKnowledgeWorkspace.tsx`
- Modify: `frontend/src/App.tsx`
- Test: manual verification + `pnpm tsc --noEmit` (workspace internals already covered by shared component).

**Interfaces:**
- Consumes: `QaKnowledgeWorkspace`, `QaWorkspaceApiClient`, `QaWorkspaceConfig` from `frontend/src/components/_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace`; the Task 7 API functions; `reindexRag`/`getReindexStatus` from `services/api/general`.
- Produces: `<GeneralKnowledgeWorkspace active={boolean} storeName={string} onTopicsChanged?={() => void} />`. Pattern reference: `frontend/src/components/hciot/HciotKnowledgeWorkspace.tsx`.

- [ ] **Step 1: Create the wrapper**

```tsx
// frontend/src/components/general/GeneralKnowledgeWorkspace.tsx
import * as gapi from '../../services/api/general';
import QaKnowledgeWorkspace, {
  type QaWorkspaceApiClient,
  type QaWorkspaceConfig,
} from '../_shared/qaKnowledgeWorkspace/QaKnowledgeWorkspace';

interface GeneralKnowledgeWorkspaceProps {
  active: boolean;
  storeName: string;
  onTopicsChanged?: () => Promise<void> | void;
}

function makeApi(storeName: string): QaWorkspaceApiClient {
  return {
    listKnowledgeFiles: () => gapi.listGeneralKnowledgeFiles(storeName),
    listTopicsAdmin: () => gapi.listGeneralTopicsAdmin(storeName),
    listImages: () => gapi.listGeneralImages(storeName),
    getReindexStatus: () => gapi.getReindexStatus('general'),
    reindex: () => gapi.default('general'),
    getKnowledgeFileContent: (filename) => gapi.getGeneralKnowledgeFileContent(filename, storeName),
    uploadKnowledgeFileWithTopic: (opts) => gapi.uploadGeneralKnowledgeFileWithTopic({ ...opts, storeName }),
    deleteKnowledgeFile: (filename) => gapi.deleteGeneralKnowledgeFile(filename, storeName),
    updateTopic: (topicId, data) => gapi.updateGeneralTopic(storeName, topicId, data),
    reorderTopics: (ids) => gapi.reorderGeneralTopics(storeName, ids),
    setCategoryHidden: (categoryId, hidden) => gapi.setGeneralCategoryHidden(storeName, categoryId, hidden),
    uploadImage: (file, imageId) => gapi.uploadGeneralImage(storeName, file, imageId),
    deleteImage: (imageId) => gapi.deleteGeneralImage(storeName, imageId),
    deleteUnusedImages: () => gapi.deleteUnusedGeneralImages(storeName),
    createTopic: (topicId, label, categoryLabel, questions) =>
      gapi.createGeneralTopic(storeName, topicId, label, categoryLabel, questions),
    updateKnowledgeFileMetadata: (filename, metadata) =>
      gapi.updateGeneralKnowledgeFileMetadata(filename, metadata, storeName),
    updateKnowledgeFileContent: (filename, content) =>
      gapi.updateGeneralKnowledgeFileContent(filename, content, storeName),
    downloadKnowledgeFile: (filename) => gapi.downloadGeneralKnowledgeFile(filename, storeName),
    getTopicMergedCsv: (topicId) => gapi.getGeneralTopicMergedCsv(topicId, storeName),
    saveTopicMergedCsv: (topicId, payload) => gapi.saveGeneralTopicMergedCsv(topicId, payload, storeName),
    parseQaCsvText: (text) => gapi.parseQaCsvText(text),
    // AI Q&A extraction disabled — these are never called when disableAiQaExtraction is true,
    // but the interface requires them; provide rejecting stubs.
    createQaExtractJob: () => Promise.reject(new Error('QA extraction disabled for general')),
    getQaExtractJob: () => Promise.reject(new Error('QA extraction disabled for general')),
    importQaExtractJob: () => Promise.reject(new Error('QA extraction disabled for general')),
  };
}

export default function GeneralKnowledgeWorkspace({ active, storeName, onTopicsChanged }: GeneralKnowledgeWorkspaceProps) {
  const config: QaWorkspaceConfig = {
    sourceType: 'general',
    api: makeApi(storeName),
    text: (_language, zh) => zh,
    disableAiQaExtraction: true,
  };
  return (
    <QaKnowledgeWorkspace
      active={active}
      language={storeName as never}
      onTopicsChanged={onTopicsChanged}
      config={config}
    />
  );
}
```

> If any stub method or signature mismatches `QaWorkspaceApiClient`, `pnpm tsc --noEmit` will flag it — align the function names with the exact names finalized in Task 7.

- [ ] **Step 2: Mount in App.tsx (admin-gated entry)**

In `frontend/src/App.tsx`, add a workspace view toggle for general (mirror HCIoT's `workspace === 'files'`), shown only when `isAdmin` and a store is selected, and render:

```tsx
{isAdmin && currentStore && (
  <GeneralKnowledgeWorkspace
    active={knowledgeWorkspaceOpen}
    storeName={currentStore}
    onTopicsChanged={() => { void handleRefreshKnowledge(); }}
  />
)}
```

Add the import, a `knowledgeWorkspaceOpen` state + a header/sidebar button to toggle it (follow the existing panel-toggle pattern in App.tsx). Reuse HCIoT's workspace CSS imports (`styles/hciot/workspace-upload*.css`) at the top of App.tsx, or — preferred — copy them to `styles/_shared/` and import from there if doing so is low-risk. Use rem/% units for any new layout (no `px`).

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: clean.

- [ ] **Step 4: Manual verification**

Bring up the stack in the worktree, log in as admin, select a general store, open the knowledge workspace. Verify: upload a valid QA CSV → it lists; create/edit a topic → it appears; upload a malformed QA CSV (q/a-like header missing `a`) → rejected with 400; check the public quick-question buttons reflect only valid QA CSV questions; trigger reindex. Confirm a second store does not see the first store's files/topics.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/general/GeneralKnowledgeWorkspace.tsx frontend/src/App.tsx frontend/src/styles
git commit -m "feat: mount general QA knowledge workspace in app"
```

---

## Self-Review Notes

- **Spec coverage:** 三塊可管理項 → Task 4 (上傳+QA/CSV), Task 5 (topics 塊速問答), Task 8 (前端整合). 塊速問答內容規則 → inherited via shared router (Task 4) + verified in Task 6 retrieval isolation. Per-store keying → Tasks 1–3. AI extraction disabled → Task 4 (`include_extract=False`) + Task 8 (`disableAiQaExtraction: true`). 不收斂舊單檔上傳 → out of scope, untouched.
- **Type consistency:** API client names finalized in Task 7 are consumed verbatim in Task 8; `tsc --noEmit` is the enforcement gate. Store factories return types match the shared base method surfaces consumed by the router.
- **Conditional task (6):** RAG isolation may already be correct (general upload already passes store_name in the language slot); Task 6 first inspects, then fixes only if needed — flagged explicitly so it isn't mistaken for a placeholder.
