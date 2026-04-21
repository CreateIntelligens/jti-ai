import pytest

from app.services.hciot.main_agent import HciotMainAgent


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


def test_hciot_agent_uses_flash_lite_for_chat():
    agent = HciotMainAgent()
    assert agent.model_name == "gemini-3.1-flash-lite-preview"


def test_extract_image_id_returns_top_citation_id():
    citations = [{"image_id": "123"}, {"image_id": "456"}]
    assert HciotMainAgent._extract_image_id(citations) == "123"

def test_extract_image_id_returns_none_if_missing():
    citations = [{"text": "no image"}]
    assert HciotMainAgent._extract_image_id(citations) is None


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

    monkeypatch.setattr("app.services.gemini_service.client", object())
    monkeypatch.setattr("app.services.hciot.main_agent.session_manager.get_session", lambda sid: session)
    
    # Mock the new RAG loop
    mock_response = type("Response", (), {
        "candidates": [type("Candidate", (), {
            "content": type("Content", (), {
                "parts": [type("Part", (), {"text": "繁體回覆"})]
            })
        })()]
    })()
    async def fake_run_tool_loop(chat_session, enriched, session, user_message):
        captured["message"] = enriched
        return mock_response, None
    monkeypatch.setattr(agent, "_run_tool_loop", fake_run_tool_loop)
    
    monkeypatch.setattr(agent, "_get_or_create_chat_session", lambda s: FakeChatSession())
    monkeypatch.setattr(agent, "_sync_history_to_db_background", lambda *a, **kw: None)

    result = await agent.chat("sid-123", "PRP是什麼")

    assert result["message"] == "繁體回覆"
    assert captured["message"].startswith("<內部狀態資訊 - 不要在回應中提及>")
    assert "必須使用繁體中文回應所有內容" in captured["message"]
    assert "使用者問題：" in captured["message"]
    assert "PRP是什麼" in captured["message"]
