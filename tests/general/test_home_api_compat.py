import hashlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests.support.app_test_support import get_test_app


app = get_test_app()


class FakeStoreRegistry:
    def __init__(self):
        self.stores = {}
        self.deleted = []

    @staticmethod
    def _matches_owner(store, owner_key_hash=None):
        if owner_key_hash:
            return store.get("owner_key_hash") == owner_key_hash
        return store.get("owner_key_hash") is None

    def list_stores(self, owner_key_hash=None):
        return [
            store
            for store in self.stores.values()
            if self._matches_owner(store, owner_key_hash)
        ]

    def create_store(self, display_name, key_index=0, owner_key_hash=None):
        name = "store_hotai"
        store = {
            "name": name,
            "display_name": display_name,
            "key_index": key_index,
            "created_at": "2026-04-30T00:00:00Z",
            "owner_key_hash": owner_key_hash,
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
    client = TestClient(app)

    response = client.get("/api/stores", headers={"Origin": "http://testserver"})

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
    assert all(store["key_index"] is None for store in stores)


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
    assert store["managed_app"] is None
    assert store["managed_language"] is None
    assert store_routes.resolve_key_index_for_store("store_hotai") == 1

    listed = client.get("/api/stores", headers={"Origin": "http://testserver"})
    assert any(item["name"] == "store_hotai" for item in listed.json())


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
    from app.routers.general import chat as general_chat
    from app.routers.general.stores import ManagedStoreConfig
    from app.services.rag import service as rag_service

    captured = {}

    class FakePipeline:
        def retrieve(self, query, language, source_type, top_k):
            captured["retrieve"] = (query, language, source_type, top_k)
            return "和泰知識", [{"title": "FAQ", "uri": "faq.csv", "text": "和泰知識"}]

    class FakeClient:
        models = SimpleNamespace(
            generate_content=lambda **_kwargs: SimpleNamespace(text="和泰回答 [cite: faq.csv]")
        )

    def fake_client_for_api_key(api_key):
        captured["api_key"] = api_key
        return FakeClient()

    def fake_resolve_store_config(_store_name, owner_key_hash=None):
        captured["owner_key_hash"] = owner_key_hash
        return ManagedStoreConfig("store_hotai", "和泰", "", "", key_index=None)

    monkeypatch.setattr(general_chat, "resolve_store_config", fake_resolve_store_config)
    monkeypatch.setattr(general_chat.gemini_service, "client", None)
    monkeypatch.setattr(general_chat, "get_client_for_api_key", fake_client_for_api_key)
    monkeypatch.setattr(general_chat.gemini_service, "gemini_with_retry", lambda callback: callback())
    monkeypatch.setattr(rag_service, "get_rag_pipeline", lambda: FakePipeline())

    answer, citations = general_chat._generate_rag_answer(
        message="請查和泰",
        session={"store_name": "store_hotai", "model": "gemini-test", "chat_history": []},
        user_gemini_api_key="AIza-user-key",
    )

    assert answer == "和泰回答"
    assert citations == [{"title": "FAQ", "uri": "faq.csv", "text": "和泰知識"}]
    assert captured["api_key"] == "AIza-user-key"
    assert captured["owner_key_hash"] == hashlib.sha256(b"AIza-user-key").hexdigest()
    assert captured["retrieve"] == ("請查和泰", "store_hotai", "general_knowledge", 5)


def test_home_can_start_and_send_general_chat(monkeypatch):
    from app.routers.general import chat as general_chat

    class FakeConversationLogger:
        def log_conversation(self, **_kwargs):
            return "log-id", 1

        def delete_turns_from(self, *_args):
            return 0

    monkeypatch.setattr(
        general_chat,
        "_generate_rag_answer",
        lambda *, message, session, **_kwargs: (
            f"回答：{message}",
            [{"title": "FAQ", "uri": "faq.csv", "text": "常見問題"}],
        ),
        raising=False,
    )
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
