import hashlib
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.support.app_test_support import get_test_app, override_admin_auth

app = get_test_app()


@pytest.fixture(autouse=True)
def override_auth_for_compat():
    cleanup = override_admin_auth(app)
    yield
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

    def create_store(self, display_name, key_index=0, owner_key_hash=None, managed_app=None):
        name = "store_hotai"
        from app.services import app_key_map
        if managed_app is not None:
            resolved_app = managed_app
        elif owner_key_hash:
            resolved_app = "general"
        else:
            resolved_app = app_key_map.resolve_app_for_key_index(key_index)
        store = {
            "name": name,
            "display_name": display_name,
            "key_index": None if owner_key_hash else key_index,
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

    key_indexes = {"jti": 2, "hciot": 3}
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
    ]
    assert stores[0]["managed_app"] == "jti"
    assert stores[0]["managed_language"] == "zh"
    assert all("file_count" in store for store in stores)
    assert [store["key_index"] for store in stores] == [2, 2, 3, 3]


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
    assert response.json()["answer"] == "和泰回答"
    assert response.json()["citations"] == [{"title": "FAQ", "uri": "faq.csv", "text": "和泰知識"}]
    assert captured["owner_key_hash"] == hashlib.sha256(b"AIza-user-key").hexdigest()


def test_home_can_start_and_send_general_chat(monkeypatch):
    from app.routers.general import chat as general_chat
    from app.services.general import main_agent as general_agent_mod

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

    monkeypatch.setattr(general_agent_mod.main_agent, "chat", fake_agent_chat)
    monkeypatch.setattr(general_chat, "_get_conversation_logger", lambda: FakeConversationLogger())

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
    assert response.json()["answer"] == "回答：常見問題"
    assert response.json()["citations"] == [{"title": "FAQ", "uri": "faq.csv", "text": "常見問題"}]


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
        "app": "hciot",
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
        "app": "hciot",
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
            "app": "hciot",
            "prompt_index": None,
        }
        mismatched_assignment = client.get("/api/stores", headers={"Origin": "http://testserver"})
        assert mismatched_assignment.status_code == 403
    finally:
        if original_verify_auth:
            app.dependency_overrides[verify_auth] = original_verify_auth
        else:
            app.dependency_overrides.pop(verify_auth, None)


def test_resolve_request_store_scope_authorization():
    from app.auth import verify_auth
    from app import deps

    client = TestClient(app)

    def set_user_auth(store_name=None, app_name=None):
        auth_info = {
            "role": "user",
            "store_name": store_name,
            "app": app_name,
            "prompt_index": None,
        }
        app.dependency_overrides[verify_auth] = lambda: auth_info

    original_verify_auth = app.dependency_overrides.get(verify_auth)

    try:
        # Case 1: User with specific store_name set (can only chat with their assigned store)
        set_user_auth(store_name="__hciot__")

        res1 = client.post(
            "/api/chat/start",
            json={"store_name": "__jti__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert res1.status_code == 200
        sid1 = res1.json()["session_id"]
        session1 = deps.get_general_chat_session_manager().get_session(sid1)
        assert session1.metadata["store_name"] == "__hciot__"

        set_user_auth(store_name="__jti__", app_name="hciot")
        app_mismatch = client.post(
            "/api/chat/start",
            json={"store_name": "__jti__", "model": "gemini-test"},
            headers={"Origin": "http://testserver"},
        )
        assert app_mismatch.status_code == 403

        # Case 2: User with null/empty store_name but assigned app (can chat with any store of that app)
        set_user_auth(store_name=None, app_name="hciot")

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
        set_user_auth(store_name=None, app_name=None)
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
