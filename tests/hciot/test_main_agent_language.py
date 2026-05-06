from types import SimpleNamespace

from app.services.hciot.main_agent import MainAgent


def test_hciot_rag_search_uses_session_language():
    agent = MainAgent()

    assert agent._get_rag_search_language_for_session(SimpleNamespace(language="en")) == "en"
    assert agent._get_rag_search_language_for_session(SimpleNamespace(language="zh")) == "zh"


def test_hciot_search_tool_does_not_force_english_queries_to_chinese():
    agent = MainAgent()
    tool = agent._rag_tool_declaration
    declaration = tool.function_declarations[0]
    description = declaration.parameters.properties["queries"].description

    assert "必須使用繁體中文" not in description
    assert "翻譯成中文" not in description
