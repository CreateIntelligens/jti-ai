"""Two LanceDBStore instances on one directory stand in for two uvicorn workers.

Regression: each worker caches its table handle, and without a read
consistency interval that handle stays pinned to the version it first opened.
A knowledge edit indexed by one worker was then invisible to the other until
the backend restarted, so answers flipped between old and new per request.
"""

import importlib
import sys
from types import ModuleType

import numpy as np
import pytest

lancedb_module = importlib.import_module("app.services.vector_store.lancedb")


def _real_lancedb() -> ModuleType:
    # test_vector_store.py swaps sys.modules["lancedb"] for a MagicMock at
    # import time; fetch the real package without leaving that swap undone.
    cached = sys.modules.get("lancedb")
    if isinstance(cached, ModuleType):
        return cached
    sys.modules.pop("lancedb", None)
    try:
        return importlib.import_module("lancedb")
    finally:
        if cached is not None:
            sys.modules["lancedb"] = cached


@pytest.fixture
def two_workers(tmp_path, monkeypatch):
    monkeypatch.setattr(lancedb_module, "lancedb", _real_lancedb())
    uri = str(tmp_path / "lancedb")
    return (
        lancedb_module.LanceDBStore(uri=uri, table_name="knowledge"),
        lancedb_module.LanceDBStore(uri=uri, table_name="knowledge"),
    )


def _vector(seed: int) -> list[float]:
    vec = np.random.default_rng(seed).random(8)
    return (vec / np.linalg.norm(vec)).tolist()


def _chunk(file_id: str, text: str, seed: int) -> dict:
    return {
        "text": text,
        "vector": _vector(seed),
        "file_id": file_id,
        "source_type": "jti_knowledge",
        "source_language": "en",
        "chunk_index": 0,
        "file_fingerprint": text,
        "image_id": "",
        "url": "",
    }


def _texts(store, seed: int) -> set[str]:
    hits = store.search(np.array(_vector(seed)), top_k=10, language="en", source_type="jti_knowledge")
    return {hit["text"] for hit in hits}


def test_insert_by_one_worker_is_visible_to_worker_with_open_handle(two_workers):
    writer, reader = two_workers
    writer.insert_chunks([_chunk("jti_001.csv", "old answer", seed=1)])
    assert _texts(reader, seed=1) == {"old answer"}

    writer.insert_chunks([_chunk("jti_041.csv", "new answer", seed=2)])

    assert "new answer" in _texts(reader, seed=2)


def test_delete_by_one_worker_is_visible_to_worker_with_open_handle(two_workers):
    writer, reader = two_workers
    writer.insert_chunks([_chunk("jti_022.csv", "stale risk claim", seed=3)])
    assert _texts(reader, seed=3) == {"stale risk claim"}

    writer.replace_file_chunks(
        "jti_022.csv",
        "jti_knowledge",
        "en",
        [_chunk("jti_022.csv", "revised answer", seed=3)],
    )

    assert _texts(reader, seed=3) == {"revised answer"}
