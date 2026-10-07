"""One search_knowledge tool call must cost one embedding request.

openVman's edge allows 2 concurrent /api/embedding connections per source. A
turn used to fire one request per AI query plus one per user-message copy (4
for a two-query turn, with the user message encoded twice), so every turn
tripped the limit and leaned on retries; when retries ran out that branch of
retrieval came back empty.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.models.session import Session
from app.services import base_agent as base_agent_module
from app.services.base_agent import BaseAgent
from app.services.rag.service import RAGPipeline


class _Agent(BaseAgent):
    @property
    def _rag_source_type(self) -> str:
        return "jti_knowledge"


class _FakePipeline:
    def __init__(self):
        self.encoded: list[list[str]] = []
        self.searched: list[tuple[str, list[float]]] = []

    def encode_queries(self, texts):
        self.encoded.append(list(texts))
        return {text: [float(i)] for i, text in enumerate(texts)}

    def retrieve_with_vector(self, query, query_vector, language="zh", source_type=None, top_k=5):
        self.searched.append((query, query_vector))
        citation = {"text": f"hit for {query}", "uri": query, "_distance": 0.1}
        return citation["text"], [citation]

    def retrieve(self, *args, **kwargs):
        raise AssertionError("per-query retrieve() would embed each query separately")


def _tool_call(queries):
    return SimpleNamespace(function_call=SimpleNamespace(name="search_knowledge", args={"queries": queries}))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_tool_call_embeds_all_queries_in_one_request(monkeypatch):
    pipeline = _FakePipeline()
    monkeypatch.setattr(base_agent_module, "get_rag_pipeline", lambda: pipeline)
    agent = _Agent(model_name="test-model")

    _, _, citations = await agent._dispatch_tool_call(
        _tool_call(["台灣 加熱菸 品牌", "heated tobacco brands Taiwan"]),
        "What heated tobacco brands are available in Taiwan?",
        Session(language="en"),
    )

    assert pipeline.encoded == [[
        "台灣 加熱菸 品牌",
        "heated tobacco brands Taiwan",
        "What heated tobacco brands are available in Taiwan?",
    ]]
    searched_queries = [query for query, _ in pipeline.searched]
    assert searched_queries.count("What heated tobacco brands are available in Taiwan?") == 2
    assert all(vector is not None for _, vector in pipeline.searched)
    assert citations


@pytest.mark.anyio
async def test_unrewritten_query_is_embedded_once(monkeypatch):
    pipeline = _FakePipeline()
    monkeypatch.setattr(base_agent_module, "get_rag_pipeline", lambda: pipeline)
    agent = _Agent(model_name="test-model")

    await agent._dispatch_tool_call(_tool_call(["Ploom X 價格"]), "Ploom X 價格", Session(language="zh"))

    assert pipeline.encoded == [["Ploom X 價格"]]
    assert [query for query, _ in pipeline.searched] == ["Ploom X 價格"]


@pytest.mark.anyio
async def test_embedding_failure_reports_no_results(monkeypatch):
    pipeline = _FakePipeline()
    pipeline.encode_queries = lambda texts: {}
    monkeypatch.setattr(base_agent_module, "get_rag_pipeline", lambda: pipeline)
    agent = _Agent(model_name="test-model")

    _, tool_result, citations = await agent._dispatch_tool_call(
        _tool_call(["q1"]), "user question", Session(language="zh")
    )

    assert "沒有找到" in tool_result
    assert not citations
    assert pipeline.searched == []


class TestPipelineEncodeQueries:
    def _pipeline(self, encode):
        pipeline = RAGPipeline()
        pipeline._embedding_service = MagicMock(encode=encode)
        pipeline._vector_store = MagicMock()
        return pipeline

    def test_encodes_unique_texts_in_one_query_call(self):
        encode = MagicMock(return_value=np.array([[1.0, 0.0], [0.0, 1.0]]))
        pipeline = self._pipeline(encode)

        vectors = pipeline.encode_queries(["a", "b", "a"])

        encode.assert_called_once_with(["a", "b"], input_type="search_query")
        assert vectors["a"].tolist() == [1.0, 0.0]
        assert vectors["b"].tolist() == [0.0, 1.0]

    def test_failure_returns_empty_mapping(self):
        pipeline = self._pipeline(MagicMock(side_effect=RuntimeError("HTTP 429")))

        assert pipeline.encode_queries(["a"]) == {}

    def test_retrieve_with_vector_skips_embedding(self):
        encode = MagicMock()
        pipeline = self._pipeline(encode)
        pipeline._vector_store.search.return_value = [
            {"text": "found", "file_id": "f.csv", "_distance": 0.2, "metadata": {}}
        ]

        kb_text, citations = pipeline.retrieve_with_vector("q", np.array([1.0, 0.0]), language="en")

        encode.assert_not_called()
        assert kb_text == "found"
        assert citations[0]["uri"] == "f.csv"
