from fastapi.testclient import TestClient

from tests.support.app_test_support import get_test_app


app = get_test_app()


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
        lambda *, message, session: (
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
