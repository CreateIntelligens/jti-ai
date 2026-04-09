import pytest

from app.services.hciot.main_agent import FILE_SEARCH_MODEL, HciotMainAgent


def test_localize_citations_uses_display_name(monkeypatch):
    fake_store = type(
        "FakeStore",
        (),
        {
            "list_files": lambda self, language: [
                {"name": "prp.csv", "display_name": "PRP.csv"},
                {"name": "helicobacter_pylori.csv", "display_name": "幽門螺旋桿菌.csv"},
            ]
        },
    )()

    monkeypatch.setattr(
        "app.services.hciot.main_agent.get_hciot_knowledge_store",
        lambda: fake_store,
    )

    citations = [
        {"title": "prp.csv", "uri": ""},
        {"title": "Reference", "uri": "file:///tmp/helicobacter_pylori.csv"},
        {"title": "Unmapped", "uri": ""},
    ]

    localized = HciotMainAgent._localize_citations("zh", citations)

    assert localized == [
        {"title": "PRP.csv", "uri": ""},
        {"title": "幽門螺旋桿菌.csv", "uri": "file:///tmp/helicobacter_pylori.csv"},
        {"title": "Unmapped", "uri": ""},
    ]


def test_hciot_agent_uses_flash_lite_for_chat_and_file_search():
    agent = HciotMainAgent()

    assert agent.model_name == "gemini-2.5-flash-lite"
    assert FILE_SEARCH_MODEL == "gemini-2.5-flash-lite"


def test_extract_top_citation_image_id_does_not_fallback_to_other_csv_rows():
    citations = [
        {
            "title": "helicobacter_pylori.csv",
            "text": "最相關問題\n最相關答案",
        }
    ]

    assert HciotMainAgent._extract_top_citation_image_id(citations) is None


def test_extract_top_citation_image_id_prefers_dedicated_img_csv_row_value(monkeypatch):
    fake_store = type(
        "FakeStore",
        (),
        {
            "get_file": lambda self, language, filename: {
                "data": b"index,q,a,img\n4,\xe7\x9b\xb8\xe9\x97\x9c\xe6\xa5\xad\xe5\x8b\x99,\xe5\x9b\x9e\xe7\xad\x94,1\n"
            }
            if filename == "topic_IMG_1.csv"
            else None
        },
    )()

    monkeypatch.setattr(
        "app.services.hciot.main_agent.get_hciot_knowledge_store",
        lambda: fake_store,
    )

    citations = [
        {
            "title": "topic_IMG_1.csv",
            "text": "index,q,a,img\n4,相關業務,回答,1",
        }
    ]

    assert HciotMainAgent._extract_top_citation_image_id(citations) == "1"


async def _fake_concurrent_result(user_message, language, session_id=None):
    return "PRP 是使用自體血液的治療方式", None


@pytest.mark.asyncio
async def test_hciot_chat_injects_session_state_into_prompt(monkeypatch):
    agent = HciotMainAgent()
    captured = {}

    class FakeChatSession:
        def send_message(self, message):
            captured["message"] = message
            part = type("Part", (), {"text": "繁體回覆"})()
            content = type("Content", (), {"parts": [part]})()
            candidate = type("Candidate", (), {"content": content})()
            return type("Response", (), {"candidates": [candidate]})()

    session = type(
        "Session",
        (),
        {
            "session_id": "sid-123",
            "language": "zh",
            "chat_history": [],
            "step": type("Step", (), {"value": "WELCOME"})(),
            "model_dump": lambda self: {"session_id": "sid-123"},
        },
    )()

    monkeypatch.setattr("app.services.hciot.main_agent._gemini_service.client", object())
    monkeypatch.setattr("app.services.hciot.main_agent.session_manager.get_session", lambda sid: session)
    monkeypatch.setattr(agent, "_concurrent_intent_and_search", _fake_concurrent_result)
    monkeypatch.setattr(agent, "_get_or_create_chat_session", lambda s: FakeChatSession())
    monkeypatch.setattr(agent, "_sync_history_to_db_background", lambda *a, **kw: None)

    result = await agent.chat("sid-123", "PRP是什麼")

    assert result["message"] == "繁體回覆"
    assert captured["message"].startswith("<內部狀態資訊 - 不要在回應中提及>")
    assert "必須使用繁體中文回應所有內容" in captured["message"]
    assert "使用者問題：" in captured["message"]
    assert "PRP是什麼" in captured["message"]
