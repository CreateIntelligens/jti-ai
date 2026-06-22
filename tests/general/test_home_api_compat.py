import hashlib
import logging
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from tests.support.app_test_support import get_test_app, override_admin_auth
_cached_app = None


def _get_app():
    # Rebuilt lazily on first access after the autouse fixture resets the cache,
    # so each test gets a fresh app with the module-reset machinery applied.
    global _cached_app
    if _cached_app is None:
        _cached_app = get_test_app()
    return _cached_app


class AppProxy:
    # Only attribute reads (app.routes, app.dependency_overrides[...]) and the
    # ASGI __call__ (TestClient(app)) are exercised — no attribute is assigned
    # through the proxy, so __setattr__/__delattr__ are intentionally omitted.
    def __getattr__(self, name):
        return getattr(_get_app(), name)

    async def __call__(self, scope, receive, send):
        await _get_app()(scope, receive, send)


app = AppProxy()


import sys

from tests.support.fake_mongo import FakeCollection


class FakeDb(dict):
    def __getitem__(self, item):
        if item not in self:
            self[item] = FakeCollection()
        return super().__getitem__(item)


fake_db = FakeDb()


@pytest.fixture(autouse=True)
def override_auth_for_compat():
    global _cached_app
    _cached_app = None
    cleanup = override_admin_auth(app)
    # Point the shared mongo mock at our fake db FOR THIS TEST ONLY, and restore
    # it on teardown — leaving it set leaks into sibling test modules that share
    # the same `app` and mongo_client mock (e.g. test_users_api,
    # test_main_agent_rag_routing).
    mongo_mock = sys.modules.get("app.services.mongo_client")
    orig_return = mongo_mock.get_mongo_db.return_value if mongo_mock else None
    if mongo_mock:
        mongo_mock.get_mongo_db.return_value = fake_db
    from app.services.session import session_manager_factory
    session_manager_factory._singletons.clear()
    yield
    _cached_app = None
    if mongo_mock:
        mongo_mock.get_mongo_db.return_value = orig_return
    session_manager_factory._singletons.clear()
    cleanup()


class FakeStoreRegistry:
    def __init__(self):
        self.stores = {}
        self.deleted = []

    @staticmethod
    def _matches_owner(store, owner_key_hash=None):
        if owner_key_hash:
            return store.get("owner_key_hash") == owner_key_hash
        return store.get("owner_key_hash") is None

    def list_stores(self, owner_key_hash=None, app=None):
        stores = [
            store
            for store in self.stores.values()
            if self._matches_owner(store, owner_key_hash)
        ]
        if app is not None:
            stores = [
                s for s in stores
                if s.get("managed_app", "general") == app
            ]
        return stores

    def create_store(self, display_name, key_index=0, owner_key_hash=None, managed_app=None, key_name=None):
        name = "store_hotai"
        from app.services import app_key_map
        if key_name is None and not owner_key_hash:
            from app.services import gemini_clients
            key_names = gemini_clients.get_key_names()
            key_name = key_names[key_index] if 0 <= key_index < len(key_names) else None
        if managed_app is not None:
            resolved_app = managed_app
        elif owner_key_hash:
            resolved_app = "general"
        elif key_name:
            resolved_app = app_key_map.resolve_app_for_key_name(key_name)
        else:
            resolved_app = app_key_map.resolve_app_for_key_index(key_index)
        store = {
            "name": name,
            "display_name": display_name,
            "key_index": None if owner_key_hash else key_index,
            "key_name": None if owner_key_hash else key_name,
            "created_at": "2026-04-30T00:00:00Z",
            "owner_key_hash": owner_key_hash,
            "managed_app": resolved_app,
        }
        self.stores[name] = store
        return store

    def get_store(self, store_name, owner_key_hash=None):
        store = self.stores.get(store_name)
        if store and self._matches_owner(store, owner_key_hash):
            return store
        return None

    def delete_store(self, store_name, owner_key_hash=None):
        self.deleted.append(store_name)
        if not self.get_store(store_name, owner_key_hash):
            return False
        return self.stores.pop(store_name, None) is not None


class FakeKnowledgeStore:
    def __init__(self):
        self.files = {}
        self.deleted_namespaces = []

    def list_files(self, language, namespace):
        return list(self.files.get((namespace, language), {}).values())

    def insert_file(
        self,
        language,
        filename,
        data,
        display_name=None,
        content_type="application/octet-stream",
        editable=True,
        namespace=None,
    ):
        item = {
            "name": filename,
            "filename": filename,
            "display_name": display_name or filename,
            "size": len(data),
            "editable": editable,
            "content_type": content_type,
        }
        self.files.setdefault((namespace, language), {})[filename] = item
        return item

    def get_file_data(self, language, filename, namespace):
        if filename not in self.files.get((namespace, language), {}):
            return None
        return b"q,a\nhi,there\n"

    def delete_file(self, language, filename, namespace):
        return self.files.get((namespace, language), {}).pop(filename, None) is not None

    def delete_by_namespace(self, namespace, language=None):
        self.deleted_namespaces.append((namespace, language))
        self.files.pop((namespace, language), None)
        return 1


def test_home_can_load_knowledge_store_list():
    from app.routers.general import stores as store_routes

    key_indexes = {"jti": 2, "hciot": 3, "esg": 4}
    original_resolver = store_routes.app_key_map.resolve_key_index_for_app
    store_routes.app_key_map.resolve_key_index_for_app = lambda app: key_indexes.get(app, -1)
    client = TestClient(app)

    try:
        response = client.get("/api/stores", headers={"Origin": "http://testserver"})
    finally:
        store_routes.app_key_map.resolve_key_index_for_app = original_resolver

    assert response.status_code == 200
    stores = response.json()
    assert [store["name"] for store in stores] == [
        "__jti__",
        "__jti__en",
        "__hciot__",
        "__hciot__en",
        "__esg__",
        "__esg__en",
    ]
    assert stores[0]["managed_app"] == "jti"
    assert stores[0]["managed_language"] == "zh"
    assert all("file_count" in store for store in stores)
    assert [store["key_index"] for store in stores] == [2, 2, 3, 3, 4, 4]


def test_managed_store_key_resolution_warns_and_falls_back(monkeypatch, caplog):
    from app.routers.general import stores as store_routes

    monkeypatch.setattr(store_routes.app_key_map, "resolve_key_index_for_app", lambda app: -1)
    caplog.set_level(logging.WARNING, logger="app.routers.general.stores")

    assert store_routes.resolve_key_index_for_store("__jti__") == 0
    assert "APP_KEY_MAP" in caplog.text
    assert "GEMINI_API_KEYS" in caplog.text


def test_store_registry_combines_owner_and_general_app_filters():
    from app.routers.general.stores import StoreRegistry

    query = StoreRegistry._merge_filters(
        StoreRegistry._owner_filter("owner-hash"),
        StoreRegistry._app_filter("general"),
    )

    assert query == {
        "$and": [
            {"owner_key_hash": "owner-hash"},
            {
                "$or": [
                    {"managed_app": "general"},
                    {"managed_app": {"$exists": False}},
                    {"managed_app": None},
                ],
            },
        ],
    }


def test_home_can_load_key_count_without_matching_key_id_route(monkeypatch):
    from app.services import gemini_clients

    monkeypatch.setattr(gemini_clients, "get_key_count", lambda: 2)
    monkeypatch.setattr(gemini_clients, "get_key_names", lambda: ["JTI", "HCIoT"])

    client = TestClient(app)

    response = client.get("/api/keys/count", headers={"Origin": "http://testserver"})

    assert response.status_code == 200
    assert response.json() == {"count": 2, "names": ["JTI", "HCIoT"]}


def test_home_can_create_key_owned_general_store(monkeypatch):
    from app.routers.general import stores as store_routes
    from app.services import gemini_clients

    registry = FakeStoreRegistry()
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    monkeypatch.setattr(gemini_clients, "get_key_count", lambda: 2)
    monkeypatch.setattr(gemini_clients, "get_key_names", lambda: ["JTI", "和泰"])

    client = TestClient(app)

    created = client.post(
        "/api/stores",
        json={"display_name": "和泰", "key_index": 1},
        headers={"Origin": "http://testserver"},
    )

    assert created.status_code == 200
    store = created.json()
    assert store["name"] == "store_hotai"
    assert store["display_name"] == "和泰"
    assert store["key_index"] == 1
    assert store["key_name"] == "和泰"
    assert store["managed_app"] == "general"
    assert store["managed_language"] is None
    assert store_routes.resolve_key_index_for_store("store_hotai") == 1

    listed = client.get("/api/stores", headers={"Origin": "http://testserver"})
    assert any(item["name"] == "store_hotai" for item in listed.json())


def test_browser_key_owned_created_store_remains_general(monkeypatch):
    from app.routers.general import stores as store_routes
    from app.services import gemini_clients

    registry = FakeStoreRegistry()
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    monkeypatch.setattr(gemini_clients, "get_key_count", lambda: 2)
    monkeypatch.setattr(gemini_clients, "get_key_names", lambda: ["General", "HCIoT"])
    monkeypatch.setattr(store_routes.app_key_map, "resolve_app_for_key_index", lambda key_index: "hciot")

    client = TestClient(app)

    created = client.post(
        "/api/stores",
        json={"display_name": "Browser Store", "key_index": 1},
        headers={"Origin": "http://testserver", "X-Gemini-API-Key": "AIza-owner"},
    )

    assert created.status_code == 200
    store = created.json()
    assert store["managed_app"] == "general"
    assert store["key_index"] is None


def test_home_can_upload_and_delete_files_for_general_store(monkeypatch):
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hotai"] = {
        "name": "store_hotai",
        "display_name": "和泰",
        "key_index": 1,
        "created_at": "2026-04-30T00:00:00Z",
    }
    knowledge_store = FakeKnowledgeStore()
    synced = []
    deleted_from_rag = []

    def fake_sync_to_rag(source_type, language, filename, data):
        synced.append((source_type, language, filename, data))

    def fake_delete_from_rag(source_type, language, filename):
        deleted_from_rag.append((source_type, language, filename))

    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    monkeypatch.setattr(store_routes, "get_knowledge_store", lambda: knowledge_store, raising=False)
    monkeypatch.setattr(store_routes, "sync_to_rag", fake_sync_to_rag, raising=False)
    monkeypatch.setattr(store_routes, "delete_from_rag", fake_delete_from_rag, raising=False)

    client = TestClient(app)

    uploaded = client.post(
        "/api/stores/store_hotai/files",
        files={"file": ("faq.csv", b"q,a\nhi,there\n", "text/csv")},
        headers={"Origin": "http://testserver"},
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["name"] == "faq.csv"
    assert synced == [("general", "store_hotai", "faq.csv", b"q,a\nhi,there\n")]

    listed = client.get("/api/stores/store_hotai/files", headers={"Origin": "http://testserver"})
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "faq.csv"

    deleted = client.delete("/api/stores/store_hotai/files/faq.csv", headers={"Origin": "http://testserver"})
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "File deleted"
    assert deleted_from_rag == [("general", "store_hotai", "faq.csv")]


def test_browser_key_owned_store_is_scoped_to_matching_key(monkeypatch):
    from app.routers.general import stores as store_routes

    owner_hash = hashlib.sha256(b"AIza-owner").hexdigest()
    registry = FakeStoreRegistry()
    registry.stores["store_hotai"] = {
        "name": "store_hotai",
        "display_name": "和泰",
        "key_index": None,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": owner_hash,
    }

    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    monkeypatch.setattr(store_routes, "get_knowledge_store", lambda: FakeKnowledgeStore(), raising=False)

    client = TestClient(app)
    headers = {"Origin": "http://testserver", "X-Gemini-API-Key": "AIza-owner"}
    wrong_headers = {"Origin": "http://testserver", "X-Gemini-API-Key": "AIza-other"}

    listed = client.get("/api/stores", headers=headers)
    hidden = client.get("/api/stores", headers=wrong_headers)
    denied = client.post("/api/chat/start", json={"store_name": "store_hotai"}, headers=wrong_headers)

    assert listed.status_code == 200
    assert any(item["name"] == "store_hotai" for item in listed.json())
    assert not any(item["name"] == "store_hotai" for item in hidden.json())
    assert denied.status_code == 404


def test_general_chat_uses_browser_gemini_key_for_general_store(monkeypatch):
    """Verify that the general chat start → message flow works end-to-end
    and correctly resolves store config when a browser API key is provided."""
    from app.routers.general import chat as general_chat
    from app.routers.general.stores import ManagedStoreConfig
    from app.services.general import main_agent as general_agent_mod

    captured = {}

    def fake_resolve_store_config(_store_name, owner_key_hash=None):
        captured["owner_key_hash"] = owner_key_hash
        return ManagedStoreConfig("store_hotai", "和泰", "", "", key_index=None)

    async def fake_agent_chat(session_id, user_message, *args, **kwargs):
        captured["chat_called"] = (session_id, user_message)
        return {
            "message": "和泰回答",
            "citations": [{"title": "FAQ", "uri": "faq.csv", "text": "和泰知識"}],
            "tool_calls": [],
        }

    class FakeConversationLogger:
        def log_conversation(self, **_kwargs):
            return "log-id", 1
        def delete_turns_from(self, *_args):
            return 0

    monkeypatch.setattr(general_chat, "resolve_store_config", fake_resolve_store_config)
    monkeypatch.setattr(general_agent_mod.main_agent, "chat", fake_agent_chat)
    monkeypatch.setattr(general_chat, "_get_conversation_logger", lambda: FakeConversationLogger())

    client = TestClient(app)
    headers = {"Origin": "http://testserver", "X-Gemini-API-Key": "AIza-user-key"}

    started = client.post(
        "/api/chat/start",
        json={"store_name": "store_hotai", "model": "gemini-test"},
        headers=headers,
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]

    response = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "message": "請查和泰"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "和泰回答"
    assert response.json()["citations"] == [{"title": "FAQ", "uri": "faq.csv", "text": "和泰知識"}]
    assert captured["owner_key_hash"] == hashlib.sha256(b"AIza-user-key").hexdigest()


def test_home_can_start_and_send_general_chat(monkeypatch):
    from app.routers.general import chat as general_chat
    from app.services.general import main_agent as general_agent_mod

    captured = {}

    class FakeConversationLogger:
        def log_conversation(self, **_kwargs):
            return "log-id", 1

        def delete_turns_from(self, *_args):
            return 0

    async def fake_agent_chat(session_id, user_message, *args, **kwargs):
        return {
            "message": f"回答：{user_message}",
            "citations": [{"title": "FAQ", "uri": "faq.csv", "text": "常見問題"}],
            "tool_calls": [],
        }

    def fake_attach_tts(response, language, manager):
        captured["tts_text"] = response.tts_text
        captured["language"] = language
        captured["manager"] = manager
        return response.model_copy(update={"tts_message_id": "tts-general"})

    monkeypatch.setattr(general_agent_mod.main_agent, "chat", fake_agent_chat)
    monkeypatch.setattr(general_chat, "_get_conversation_logger", lambda: FakeConversationLogger())
    monkeypatch.setattr(general_chat, "_get_tts_manager", lambda: "general-manager", raising=False)
    monkeypatch.setattr(
        general_chat,
        "attach_tts_message_id",
        fake_attach_tts,
        raising=False,
    )

    client = TestClient(app)

    started = client.post(
        "/api/chat/start",
        json={"store_name": "__hciot__", "model": "gemini-test"},
        headers={"Origin": "http://testserver"},
    )

    assert started.status_code == 200
    session_id = started.json()["session_id"]

    response = client.post(
        "/api/chat/message",
        json={"session_id": session_id, "message": "常見問題"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "回答：常見問題"
    assert response.json()["citations"] == [{"title": "FAQ", "uri": "faq.csv", "text": "常見問題"}]
    assert response.json()["tts_message_id"] == "tts-general"
    assert captured == {
        "tts_text": "回答：常见问题",
        "language": "zh",
        "manager": "general-manager",
    }


def test_list_stores_filtering_by_app(monkeypatch):
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hciot_dyn"] = {
        "name": "store_hciot_dyn",
        "display_name": "HCIoT Dynamic",
        "key_index": 1,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "hciot",
    }
    registry.stores["store_jti_dyn"] = {
        "name": "store_jti_dyn",
        "display_name": "JTI Dynamic",
        "key_index": 2,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "jti",
    }
    registry.stores["store_gen_dyn"] = {
        "name": "store_gen_dyn",
        "display_name": "General Dynamic",
        "key_index": 0,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }

    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)

    key_indexes = {"jti": 2, "hciot": 3}
    original_resolver = store_routes.app_key_map.resolve_key_index_for_app
    store_routes.app_key_map.resolve_key_index_for_app = lambda app: key_indexes.get(app, -1)
    client = TestClient(app)

    try:
        response_hciot = client.get("/api/stores?app=hciot", headers={"Origin": "http://testserver"})
        assert response_hciot.status_code == 200
        stores_hciot = response_hciot.json()
        assert set(store["name"] for store in stores_hciot) == {
            "__hciot__",
            "__hciot__en",
            "store_hciot_dyn",
        }
        for store in stores_hciot:
            assert store["managed_app"] == "hciot"

        response_jti = client.get("/api/stores?app=jti", headers={"Origin": "http://testserver"})
        assert response_jti.status_code == 200
        stores_jti = response_jti.json()
        assert set(store["name"] for store in stores_jti) == {
            "__jti__",
            "__jti__en",
            "store_jti_dyn",
        }
        for store in stores_jti:
            assert store["managed_app"] == "jti"

    finally:
        store_routes.app_key_map.resolve_key_index_for_app = original_resolver


def test_user_without_store_lists_only_own_app_stores(monkeypatch):
    from app.auth import verify_auth
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hciot_dyn"] = {
        "name": "store_hciot_dyn",
        "display_name": "HCIoT Dynamic",
        "key_index": 1,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "hciot",
    }
    registry.stores["store_jti_dyn"] = {
        "name": "store_jti_dyn",
        "display_name": "JTI Dynamic",
        "key_index": 2,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "jti",
    }
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    monkeypatch.setattr(
        store_routes.app_key_map,
        "resolve_key_index_for_app",
        lambda app_name: {"jti": 2, "hciot": 3}.get(app_name, -1),
    )

    original_verify_auth = app.dependency_overrides.get(verify_auth)
    app.dependency_overrides[verify_auth] = lambda: {
        "role": "user",
        "store_name": None,
        "scope": "hciot",
        "prompt_index": None,
    }
    client = TestClient(app)

    try:
        response = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert response.status_code == 200
        assert {store["name"] for store in response.json()} == {
            "__hciot__",
            "__hciot__en",
            "store_hciot_dyn",
        }

        cross_app = client.get("/api/stores?app=jti", headers={"Origin": "http://testserver"})
        assert cross_app.status_code == 403
    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)


def test_legacy_key_index_scope_is_rejected(monkeypatch):
    from app.auth import verify_auth
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hotai"] = {
        "name": "store_hotai",
        "display_name": "和泰汽車",
        "key_index": 1,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }
    registry.stores["store_poc2"] = {
        "name": "store_poc2",
        "display_name": "POC2",
        "key_index": 2,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)

    original_verify_auth = app.dependency_overrides.get(verify_auth)
    app.dependency_overrides[verify_auth] = lambda: {
        "role": "user",
        "store_name": None,
        "scope": "key:1",
        "prompt_index": None,
    }
    client = TestClient(app)

    try:
        response = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert response.status_code == 400
        assert "key_name" in response.json()["detail"]

        admin_query = client.get("/api/stores?app=key:1", headers={"Origin": "http://testserver"})
        assert admin_query.status_code == 400
        assert "key_name" in admin_query.json()["detail"]
    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)


def test_user_key_name_scope_survives_key_order_changes(monkeypatch):
    from app.auth import verify_auth
    from app import deps
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hotai"] = {
        "name": "store_hotai",
        "display_name": "和泰汽車",
        "key_index": 1,
        "key_name": "和泰汽車",
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }
    registry.stores["store_poc2"] = {
        "name": "store_poc2",
        "display_name": "POC2",
        "key_index": 2,
        "key_name": "POC2",
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    monkeypatch.setattr(
        store_routes.gemini_clients,
        "resolve_key_index_by_name",
        lambda name: {"和泰汽車": 0, "POC1": 1, "POC2": 2}.get(name, -1),
    )
    # file_count for managed stores reads the real namespaced knowledge store
    # (Mongo-backed, module-level singleton cache). This test only asserts store
    # identity/order, so pin file listings to empty — otherwise the count leaks
    # real seed data (e.g. the ESG KB) and varies with test ordering.
    monkeypatch.setattr(store_routes, "_list_store_files", lambda config: [])

    scope = f"key_name:{quote('和泰汽車')}"
    original_verify_auth = app.dependency_overrides.get(verify_auth)
    app.dependency_overrides[verify_auth] = lambda: {
        "role": "user",
        "store_name": None,
        "scope": scope,
        "prompt_index": None,
    }
    client = TestClient(app)

    try:
        response = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "__esg__",
                "display_name": "ESG 中文",
                "file_count": 0,
                "created_at": None,
                "managed_app": "esg",
                "managed_language": "zh",
                "key_index": 0,
            },
            {
                "name": "__esg__en",
                "display_name": "ESG English",
                "file_count": 0,
                "created_at": None,
                "managed_app": "esg",
                "managed_language": "en",
                "key_index": 0,
            },
            {
                "name": "store_hotai",
                "display_name": "和泰汽車",
                "file_count": 0,
                "created_at": "2026-04-30T00:00:00Z",
                "managed_app": "general",
                "managed_language": None,
                "key_index": 0,
                "key_name": "和泰汽車",
            }
        ]

        cross_scope = client.get(
            f"/api/stores?app=key_name:{quote('POC2')}",
            headers={"Origin": "http://testserver"},
        )
        assert cross_scope.status_code == 403

        started = client.post(
            "/api/chat/start",
            json={"store_name": "store_hotai", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert started.status_code == 200
        session = deps.get_general_chat_session_manager().get_session(started.json()["session_id"])
        assert session.metadata["store_name"] == "store_hotai"

        denied = client.post(
            "/api/chat/start",
            json={"store_name": "store_poc2", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert denied.status_code == 403
    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)


def test_user_with_store_lists_only_assigned_store(monkeypatch):
    from app.auth import verify_auth
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hciot_dyn"] = {
        "name": "store_hciot_dyn",
        "display_name": "HCIoT Dynamic",
        "key_index": 1,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "hciot",
    }
    registry.stores["store_jti_dyn"] = {
        "name": "store_jti_dyn",
        "display_name": "JTI Dynamic",
        "key_index": 2,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "jti",
    }
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)

    original_verify_auth = app.dependency_overrides.get(verify_auth)
    app.dependency_overrides[verify_auth] = lambda: {
        "role": "user",
        "store_name": "store_hciot_dyn",
        "scope": "hciot",
        "prompt_index": None,
    }
    client = TestClient(app)

    try:
        response = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert response.status_code == 200
        assert [store["name"] for store in response.json()] == ["store_hciot_dyn"]

        cross_app = client.get("/api/stores?app=jti", headers={"Origin": "http://testserver"})
        assert cross_app.status_code == 403

        app.dependency_overrides[verify_auth] = lambda: {
            "role": "user",
            "store_name": "store_jti_dyn",
            "scope": "hciot",
            "prompt_index": None,
        }
        mismatched_assignment = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert mismatched_assignment.status_code == 403

        app.dependency_overrides[verify_auth] = lambda: {
            "role": "user",
            "store_name": "store_hciot_dyn",
            "scope": None,
            "prompt_index": None,
        }
        store_only_assignment = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert store_only_assignment.status_code == 200
        assert [store["name"] for store in store_only_assignment.json()] == ["store_hciot_dyn"]
    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)


def test_resolve_request_store_scope_authorization():
    from app.auth import verify_auth
    from app import deps

    client = TestClient(app)

    def set_user_auth(store_name=None, scope=None):
        auth_info = {
            "role": "user",
            "store_name": store_name,
            "scope": scope,
            "prompt_index": None,
        }
        app.dependency_overrides[verify_auth] = lambda: auth_info

    original_verify_auth = app.dependency_overrides.get(verify_auth)

    try:
        # Case 1: User bound to a specific store is pinned to it.
        set_user_auth(store_name="__hciot__")

        # 1a: no requested store → bind back to the assigned store (200).
        res1 = client.post(
            "/api/chat/start",
            json={"model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res1.status_code == 200
        sid1 = res1.json()["session_id"]
        session1 = deps.get_general_chat_session_manager().get_session(sid1)
        assert session1.metadata["store_name"] == "__hciot__"

        # 1b: requesting a DIFFERENT store is rejected, not silently rebound.
        res1b = client.post(
            "/api/chat/start",
            json={"store_name": "__jti__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res1b.status_code == 403

        set_user_auth(store_name="__jti__", scope="hciot")
        app_mismatch = client.post(
            "/api/chat/start",
            json={"store_name": "__jti__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert app_mismatch.status_code == 403

        # Case 2: User with null/empty store_name but assigned app (can chat with any store of that app)
        set_user_auth(store_name=None, scope="hciot")

        res2 = client.post(
            "/api/chat/start",
            json={"store_name": "__hciot__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res2.status_code == 200
        sid2 = res2.json()["session_id"]
        session2 = deps.get_general_chat_session_manager().get_session(sid2)
        assert session2.metadata["store_name"] == "__hciot__"

        res3 = client.post(
            "/api/chat/start",
            json={"store_name": "__hciot__en", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res3.status_code == 200
        sid3 = res3.json()["session_id"]
        session3 = deps.get_general_chat_session_manager().get_session(sid3)
        assert session3.metadata["store_name"] == "__hciot__en"

        # Case 3: User with null/empty store_name getting 403 when trying to access a store of another app
        res4 = client.post(
            "/api/chat/start",
            json={"store_name": "__jti__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res4.status_code == 403

        # User has null/empty store_name and NO assigned app
        set_user_auth(store_name=None, scope=None)
        res5 = client.post(
            "/api/chat/start",
            json={"store_name": "__hciot__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res5.status_code == 403

    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)


def test_resolve_request_store_rejects_legacy_key_index_scope(monkeypatch):
    from app.auth import verify_auth
    from app.routers.general import stores as store_routes

    registry = FakeStoreRegistry()
    registry.stores["store_hotai"] = {
        "name": "store_hotai",
        "display_name": "和泰汽車",
        "key_index": 1,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }
    registry.stores["store_poc2"] = {
        "name": "store_poc2",
        "display_name": "POC2",
        "key_index": 2,
        "created_at": "2026-04-30T00:00:00Z",
        "owner_key_hash": None,
        "managed_app": "general",
    }
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)

    original_verify_auth = app.dependency_overrides.get(verify_auth)
    app.dependency_overrides[verify_auth] = lambda: {
        "role": "user",
        "store_name": None,
        "scope": "key:1",
        "prompt_index": None,
    }
    client = TestClient(app)

    try:
        rejected = client.post(
            "/api/chat/start",
            json={"store_name": "store_hotai", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert rejected.status_code == 400
        assert "key_name" in rejected.json()["detail"]
    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)
