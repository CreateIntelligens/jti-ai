"""RAG routing for the general MainAgent.

Locks in the write/read symmetry that broke general-store retrieval:

- Managed stores (the fixed JTI/HCIoT knowledge pages) write chunks keyed by
  language (zh/en) and under "<app>_knowledge", so reads must use managed_language.
- Dynamic stores — general OR key-mapped — are uploaded via the general namespace,
  keyed by store_name and under "general_knowledge". They carry
  managed_language="" (and managed_app may be "general" or even an app name via a
  key mapping), so reads MUST key by store_name, not by managed_app truthiness.

Regression guard for the bug where a general store returned no documents because
the search language resolved to None instead of the store_name.
"""

from types import SimpleNamespace

import pytest

from app.services.general.main_agent import MainAgent
from app.services.hciot.main_agent import _RAG_TOOL as HCIOT_RAG_TOOL
from app.services.jti.main_agent import _RAG_TOOL as JTI_RAG_TOOL


def _session(**metadata):
    return SimpleNamespace(metadata=metadata)


def _tool_description(tool):
    return tool.function_declarations[0].description


def test_managed_store_searches_by_language():
    agent = MainAgent()
    session = _session(store_name="__jti__", managed_app="jti", managed_language="zh")

    assert agent._get_rag_search_language_for_session(session) == "zh"
    assert agent._get_rag_source_type_for_session(session) == ["jti_knowledge"]


def test_general_store_searches_by_store_name():
    agent = MainAgent()
    session = _session(store_name="store_8ad3a8fa4837", managed_app="general", managed_language="")

    # The whole point: a general store must search under its own store_name and the
    # general_knowledge namespace — never fall back to None just because managed_app
    # is the truthy string "general".
    assert agent._get_rag_search_language_for_session(session) == "store_8ad3a8fa4837"
    assert agent._get_rag_source_type_for_session(session) == ["general_knowledge"]


def test_key_mapped_dynamic_store_still_uses_general_namespace():
    agent = MainAgent()
    # A dynamic store created under a key mapped to an app carries managed_app="jti"
    # but is still uploaded via the general namespace (keyed by store_name), so it
    # must read from general_knowledge by store_name, not jti_knowledge by language.
    session = _session(store_name="store_keymapped", managed_app="jti", managed_language="")

    assert agent._get_rag_search_language_for_session(session) == "store_keymapped"
    assert agent._get_rag_source_type_for_session(session) == ["general_knowledge"]


@pytest.mark.parametrize(
    ("store_name", "managed_app", "expected_tool"),
    [
        ("__jti__", "jti", JTI_RAG_TOOL),
        ("__hciot__", "hciot", HCIOT_RAG_TOOL),
    ],
)
def test_managed_store_uses_app_rag_tool_template(store_name, managed_app, expected_tool):
    agent = MainAgent()
    session = _session(store_name=store_name, managed_app=managed_app, managed_language="zh")

    assert _tool_description(agent._get_rag_tool_declaration_for_session(session)) == _tool_description(expected_tool)


def test_dynamic_store_uses_general_rag_tool_template():
    agent = MainAgent()
    session = _session(store_name="store_keymapped", managed_app="jti", managed_language="")

    assert _tool_description(agent._get_rag_tool_declaration_for_session(session)) == _tool_description(agent._rag_tool_declaration)
