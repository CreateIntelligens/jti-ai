"""General per-store topics + images router tests.

Verify topic CRUD and image upload/get/delete are isolated per store_name,
through the HTTP surface, backed by an in-memory fake Mongo. get_mongo_db is
patched on the base/store modules directly (sibling test modules reload them
and rebind their imported reference) and restored on teardown to avoid leaks.
"""

import sys

import pytest
from fastapi.testclient import TestClient

from tests.support.app_test_support import install_app_import_mocks


class FakeCursor(list):
    def sort(self, key, direction=None):
        # Support both Mongo call forms: sort("field", 1) and sort([("a",1),("b",1)]).
        if isinstance(key, list):
            keys = key
        else:
            keys = [(key, direction if direction is not None else 1)]
        items = list(self)
        for field, dir_ in reversed(keys):
            items.sort(key=lambda it: it.get(field, ""), reverse=dir_ < 0)
        return FakeCursor(items)


class FakeCollection:
    _id_seq = 0

    def __init__(self):
        self.docs: list[dict] = []

    def create_index(self, *args, **kwargs):
        pass

    @classmethod
    def _next_id(cls):
        cls._id_seq += 1
        return f"oid-{cls._id_seq}"

    @staticmethod
    def _matches(doc, query):
        import re

        for k, v in query.items():
            if isinstance(v, dict) and "$in" in v:
                if doc.get(k) not in v["$in"]:
                    return False
            elif isinstance(v, dict) and "$regex" in v:
                flags = re.IGNORECASE if "i" in v.get("$options", "") else 0
                if not re.search(v["$regex"], str(doc.get(k) or ""), flags):
                    return False
            elif doc.get(k) != v:
                return False
        return True

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
        from unittest.mock import MagicMock

        stored = dict(doc)
        stored.setdefault("_id", self._next_id())
        self.docs.append(stored)
        return MagicMock(inserted_id=stored["_id"])

    def delete_one(self, query):
        from unittest.mock import MagicMock

        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    def delete_many(self, query):
        from unittest.mock import MagicMock

        kept = [d for d in self.docs if not self._matches(d, query)]
        removed = len(self.docs) - len(kept)
        self.docs[:] = kept
        return MagicMock(deleted_count=removed)

    def update_one(self, query, update, upsert=False):
        from unittest.mock import MagicMock

        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return MagicMock(matched_count=1)
        if upsert:
            self.docs.append({**update.get("$setOnInsert", {}), **update.get("$set", {})})
        return MagicMock(matched_count=0)

    def find_one_and_update(self, query, update, upsert=False, return_document=None, **kwargs):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return dict(doc)
        if upsert:
            new_doc = {**query, **update.get("$setOnInsert", {}), **update.get("$set", {})}
            new_doc.setdefault("_id", self._next_id())
            self.docs.append(new_doc)
            return dict(new_doc)
        return None

    def bulk_write(self, operations, ordered=False):
        from unittest.mock import MagicMock

        matched = 0
        for op in operations:
            for doc in self.docs:
                if self._matches(doc, op._filter):
                    doc.update(op._doc.get("$set", {}))
                    matched += 1
                    break
        return MagicMock(matched_count=matched)


fake_db = {
    "general_topics": FakeCollection(),
    "general_categories": FakeCollection(),
    "general_images": FakeCollection(),
    "general_knowledge_files": FakeCollection(),
}

install_app_import_mocks()
sys.modules["app.services.mongo_client"].get_mongo_db.return_value = fake_db

from app.main import app  # noqa: E402
from app.auth import verify_auth  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_auth():
    app.dependency_overrides[verify_auth] = lambda: {"role": "super_admin", "store_name": None}
    _get_db = lambda *_a, **_k: fake_db  # noqa: E731
    import app.services._shared.qa_kb.topic_store_base as tb_base
    import app.services._shared.qa_kb.knowledge_store_base as kb_base
    import app.services.general.image_store as img_mod
    import app.services.general.knowledge_store as ks_mod
    _orig_tb, _orig_kb, _orig_img = tb_base.get_mongo_db, kb_base.get_mongo_db, img_mod.get_mongo_db
    tb_base.get_mongo_db = _get_db
    kb_base.get_mongo_db = _get_db
    img_mod.get_mongo_db = _get_db
    img_mod._image_store = None
    ks_mod._knowledge_store = None
    for coll in fake_db.values():
        coll.docs.clear()
    yield
    tb_base.get_mongo_db = _orig_tb
    kb_base.get_mongo_db = _orig_kb
    img_mod.get_mongo_db = _orig_img
    img_mod._image_store = None
    ks_mod._knowledge_store = None
    app.dependency_overrides.pop(verify_auth, None)


def test_topic_crud_isolated_by_store():
    r = client.post(
        "/api/general-admin/stores/store-t/topics/",
        json={
            "topic_id": "faq/greet",
            "labels": "Greetings",
            "category_labels": "FAQ",
            "questions": ["hi"],
        },
    )
    assert r.status_code in (200, 201), r.text

    # Response shape matches HCIoT: {categories: [{id, label, topics: [...]}]}.
    cats = client.get("/api/general/stores/store-t/topics").json()["categories"]
    topic_ids = [t["id"] for c in cats for t in c["topics"]]
    assert "faq/greet" in topic_ids

    # Isolation: a different store sees no categories.
    assert client.get("/api/general/stores/store-u/topics").json()["categories"] == []

    d = client.delete("/api/general-admin/stores/store-t/topics/faq/greet")
    assert d.status_code == 200, d.text
    assert client.get("/api/general/stores/store-t/topics").json()["categories"] == []


def test_topics_all_is_admin_only_not_public():
    """The unfiltered `/topics/all` listing exposes hidden topics/questions, so
    it must be mounted ONLY under the authed /api/general-admin prefix — never
    under the public /api/general prefix (regression guard for an IDOR where it
    was mistakenly registered on the public router)."""
    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/api/general-admin/stores/{store_name}/topics/all" in routes
    assert "/api/general/stores/{store_name}/topics/all" not in routes
    # The slim listing stays public.
    assert "/api/general/stores/{store_name}/topics" in routes


def test_image_upload_get_delete_isolated():
    up = client.post(
        "/api/general-admin/stores/store-i/images",
        files={"file": ("logo.png", b"\x89PNG\r\n", "image/png")},
        data={"image_id": "logo"},
    )
    assert up.status_code == 201, up.text

    got = client.get("/api/general/stores/store-i/images/logo")
    assert got.status_code == 200
    assert got.content == b"\x89PNG\r\n"
    # Defense-in-depth against stored XSS: never sniff, sandboxed CSP.
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in got.headers["content-security-policy"]
    assert got.headers["content-type"].startswith("image/png")

    # Isolation: a different store has no such image.
    miss = client.get("/api/general/stores/store-j/images/logo")
    assert miss.status_code == 404

    listed = client.get("/api/general-admin/stores/store-i/images")
    assert "logo" in [i["image_id"] for i in listed.json()["images"]]

    d = client.delete("/api/general-admin/stores/store-i/images/logo")
    assert d.status_code == 200
    assert client.get("/api/general/stores/store-i/images/logo").status_code == 404


def test_non_allowlisted_content_type_served_as_attachment():
    """A malicious upload claiming an executable MIME (e.g. text/html or SVG)
    must be served as an opaque, non-rendering download — not with its declared
    type — to prevent stored XSS."""
    client.post(
        "/api/general-admin/stores/store-x/images",
        files={"file": ("evil.svg", b"<svg onload=alert(1)>", "image/svg+xml")},
        data={"image_id": "evil"},
    )
    got = client.get("/api/general/stores/store-x/images/evil")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("application/octet-stream")
    assert got.headers["content-disposition"] == "attachment"
    assert got.headers["x-content-type-options"] == "nosniff"


def test_csv_sync_stores_questions_flat_for_single_language():
    """Regression: syncing a topic's questions from a validated QA CSV must
    store them so general (single-language, store_name in the `language` slot)
    can read them back. Previously the shared sync wrote {lang: q, other: []}
    where other == lang, collapsing to {lang: []} and wiping every question."""
    from app.routers.general.knowledge import _make_config
    from app.routers._shared.qa_kb_sync import _sync_topic_questions_from_store
    from app.services.general.knowledge_store import get_general_knowledge_store
    from app.services.general.topic_store import get_general_topic_store

    store_name = "store-sync"
    topic_id = "faq/greet"
    # Seed a validated QA CSV for the topic under the general knowledge store.
    get_general_knowledge_store().insert_file(
        store_name,
        "greet.csv",
        b"index,q,a\n1,Hi there,Hello!\n2,Bye,Goodbye\n",
        content_type="text/csv",
        topic_id=topic_id,
        category_label="FAQ",
        topic_label="Greet",
    )

    synced = _sync_topic_questions_from_store(
        _make_config(),
        language=store_name,
        topic_id=topic_id,
        topic_label="Greet",
        category_label="FAQ",
        hidden_questions=None,
    )
    assert synced is True

    topic = get_general_topic_store(store_name).get_topic(topic_id)
    assert topic is not None
    # Questions stored as a flat list (not a partition dict), and not wiped.
    assert topic["questions"] == ["Hi there", "Bye"]
    assert not isinstance(topic["questions"], dict)
