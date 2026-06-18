"""General per-store knowledge router tests (app/routers/general/knowledge.py).

The shared qa_kb router keys data by its ``language`` field, which general
repurposes to carry ``store_name``. These tests verify upload/list/delete
roundtrip and per-store isolation through the HTTP surface, backed by an
in-memory fake Mongo collection. RAG indexing background tasks are patched
to no-ops so the test stays focused on routing + store CRUD.
"""

import importlib
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.support.app_test_support import install_app_import_mocks


class FakeCursor(list):
    def sort(self, key, direction):
        reverse = direction < 0
        return FakeCursor(sorted(self, key=lambda item: item.get(key, ""), reverse=reverse))


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def create_index(self, *args, **kwargs):
        pass

    @staticmethod
    def _matches(doc, query):
        return all(doc.get(k) == v for k, v in query.items())

    @staticmethod
    def _project(doc, projection):
        if not projection:
            return dict(doc)
        include = [k for k, v in projection.items() if v]
        if include:
            return {k: doc.get(k) for k in include if k in doc}
        result = dict(doc)
        for k, v in projection.items():
            if v == 0:
                result.pop(k, None)
        return result

    def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._project(doc, projection)
        return None

    def find(self, query, projection=None):
        return FakeCursor(
            [self._project(d, projection) for d in self.docs if self._matches(d, query)]
        )

    def count_documents(self, query, limit=0):
        n = sum(1 for d in self.docs if self._matches(d, query))
        return min(n, limit) if limit else n

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="fake-id")

    def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return MagicMock(matched_count=1)
        if upsert:
            self.docs.append({**update.get("$setOnInsert", {}), **update.get("$set", {})})
        return MagicMock(matched_count=0)


fake_db = {
    "general_knowledge_files": FakeCollection(),
    "general_topics": FakeCollection(),
    "general_categories": FakeCollection(),
}

install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

# Reload knowledge store base so it binds to the fake db, then the app.
importlib.reload(importlib.import_module("app.services._shared.qa_kb.knowledge_store_base"))
importlib.reload(importlib.import_module("app.services._shared.qa_kb.topic_store_base"))
importlib.reload(importlib.import_module("app.services.general.knowledge_store"))
importlib.reload(importlib.import_module("app.services.general.topic_store"))

from app.main import app  # noqa: E402
from app.auth import verify_auth  # noqa: E402

# Patch RAG indexing background tasks to no-ops (keep tests off the embedding stack).
import app.routers.knowledge_utils as knowledge_utils  # noqa: E402

knowledge_utils.sync_to_rag = lambda *a, **k: None
knowledge_utils.delete_from_rag = lambda *a, **k: None
import app.routers._shared.qa_kb_upload as qa_kb_upload  # noqa: E402

# Records (source_type, language, filename) for each RAG sync triggered by upload,
# so we can assert general indexes chunks keyed by store_name (the `language` slot).
rag_sync_calls: list[tuple] = []


def _record_sync(source_type, language, filename, *_a, **_k):
    rag_sync_calls.append((source_type, language, filename))


qa_kb_upload.sync_to_rag = _record_sync
qa_kb_upload.delete_from_rag = lambda *a, **k: None

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_auth():
    app.dependency_overrides[verify_auth] = lambda: {"role": "super_admin", "store_name": None}
    # Sibling test modules reload the qa_kb base modules and rebind their
    # `from app.services.mongo_client import get_mongo_db` reference to a fresh
    # MagicMock. Patch get_mongo_db directly on every module that imported it
    # by name (not just sys.modules) so our fake db wins regardless of order.
    _get_db = lambda *_a, **_k: fake_db  # noqa: E731
    import app.services._shared.qa_kb.knowledge_store_base as kb_base
    import app.services._shared.qa_kb.topic_store_base as tb_base
    _orig_kb, _orig_tb = kb_base.get_mongo_db, tb_base.get_mongo_db
    kb_base.get_mongo_db = _get_db
    tb_base.get_mongo_db = _get_db
    # Reset cached store singleton so it rebinds to this db.
    import app.services.general.knowledge_store as ks_mod
    ks_mod._knowledge_store = None
    for coll in fake_db.values():
        coll.docs.clear()
    rag_sync_calls.clear()
    # Reset the shared upload rate limiter so this test neither trips it nor
    # leaks request history into sibling upload tests (shared module global).
    knowledge_utils.upload_rate_limiter.requests.clear()
    yield
    # Restore the base modules' get_mongo_db so this test does not leak its fake
    # db into sibling test modules.
    kb_base.get_mongo_db = _orig_kb
    tb_base.get_mongo_db = _orig_tb
    ks_mod._knowledge_store = None
    knowledge_utils.upload_rate_limiter.requests.clear()
    app.dependency_overrides.pop(verify_auth, None)


def test_upload_list_delete_roundtrip_and_isolation():
    csv = b"q,a\nHello,Hi there\n"
    r = client.post(
        "/api/general-admin/knowledge/upload/",
        params={"language": "store-x"},
        files={"file": ("faq.csv", csv, "text/csv")},
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/general-admin/knowledge/files/", params={"language": "store-x"})
    assert r.status_code == 200
    names = [f["filename"] for f in r.json()["files"]]
    assert "faq.csv" in names

    # Isolation: store-y must not see store-x's file.
    r2 = client.get("/api/general-admin/knowledge/files/", params={"language": "store-y"})
    assert "faq.csv" not in [f["filename"] for f in r2.json()["files"]]

    d = client.delete(
        "/api/general-admin/knowledge/files/faq.csv", params={"language": "store-x"}
    )
    assert d.status_code == 200, d.text
    r3 = client.get("/api/general-admin/knowledge/files/", params={"language": "store-x"})
    assert "faq.csv" not in [f["filename"] for f in r3.json()["files"]]


def test_rag_sync_keyed_by_store_name():
    """General indexes chunks into RAG keyed by store_name (carried in the
    `language` slot) under source_type 'general' — the contract that keeps
    retrieval isolated per store, matching how general chat retrieves
    (source_type='general_knowledge', language=store_name)."""
    csv = b"q,a\nWhat is X,X is a thing\n"
    r = client.post(
        "/api/general-admin/knowledge/upload/",
        params={"language": "store-x"},
        files={"file": ("x.csv", csv, "text/csv")},
    )
    assert r.status_code == 200, r.text

    assert rag_sync_calls, "upload did not trigger a RAG sync"
    source_types = {c[0] for c in rag_sync_calls}
    languages = {c[1] for c in rag_sync_calls}
    assert source_types == {"general"}
    assert languages == {"store-x"}  # store_name occupies the language slot
    # A different store would index under its own key, never store-x's.
    assert "store-y" not in languages
