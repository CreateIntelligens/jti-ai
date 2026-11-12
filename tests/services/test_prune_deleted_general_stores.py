"""Vectors of a general store deleted on another host must not linger here.

Each host keeps its own LanceDB. Backfill only visits stores that still exist,
so a store deleted through one host's admin API kept its chunks on the other
host forever (an attacker's probe store survived this way after 10/6).
"""

import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

lancedb_module = importlib.import_module("app.services.vector_store.lancedb")
backfill_module = importlib.import_module("app.services.rag.backfill")


def _backfill_with_store(store):
    service = object.__new__(backfill_module.BackfillService)
    patcher = patch.object(
        backfill_module.BackfillService, "lancedb_store", new_callable=PropertyMock, return_value=store
    )
    patcher.start()
    return service, patcher


def test_deletes_only_stores_missing_from_registry():
    store = MagicMock()
    store.list_source_languages.return_value = {"store-live", "store-gone", "store-also-gone"}
    service, patcher = _backfill_with_store(store)
    try:
        service.prune_deleted_general_stores({"store-live"})
    finally:
        patcher.stop()

    store.list_source_languages.assert_called_once_with("general_knowledge")
    deleted = sorted(c.args for c in store.delete_by_source_language.call_args_list)
    assert deleted == [("general_knowledge", "store-also-gone"), ("general_knowledge", "store-gone")]


def test_never_prunes_system_managed_store_names():
    store = MagicMock()
    store.list_source_languages.return_value = {"__hciot__", "store-gone"}
    service, patcher = _backfill_with_store(store)
    try:
        service.prune_deleted_general_stores({"store-live"})
    finally:
        patcher.stop()

    assert [c.args for c in store.delete_by_source_language.call_args_list] == [("general_knowledge", "store-gone")]


def test_empty_registry_never_wipes_every_store():
    store = MagicMock()
    store.list_source_languages.return_value = {"store-a", "store-b"}
    service, patcher = _backfill_with_store(store)
    try:
        service.prune_deleted_general_stores(set())
    finally:
        patcher.stop()

    store.delete_by_source_language.assert_not_called()


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


def _chunk(file_id: str, source_type: str, source_language: str, seed: int) -> dict:
    vec = np.random.default_rng(seed).random(8)
    return {
        "text": f"{source_language}/{file_id}",
        "vector": (vec / np.linalg.norm(vec)).tolist(),
        "file_id": file_id,
        "source_type": source_type,
        "source_language": source_language,
        "chunk_index": 0,
        "file_fingerprint": file_id,
        "image_id": "",
        "url": "",
    }


@pytest.fixture
def real_store(tmp_path, monkeypatch):
    monkeypatch.setattr(lancedb_module, "lancedb", _real_lancedb())
    return lancedb_module.LanceDBStore(uri=str(tmp_path / "lancedb"), table_name="knowledge")


def test_lancedb_lists_and_deletes_one_partition(real_store):
    real_store.insert_chunks([
        _chunk("a.txt", "general_knowledge", "store-live", 1),
        _chunk("b.txt", "general_knowledge", "store-gone", 2),
        _chunk("c.txt", "general_knowledge", "store-o'quote", 3),
        _chunk("d.txt", "jti_knowledge", "store-gone", 4),
    ])

    assert real_store.list_source_languages("general_knowledge") == {"store-live", "store-gone", "store-o'quote"}

    real_store.delete_by_source_language("general_knowledge", "store-gone")
    real_store.delete_by_source_language("general_knowledge", "store-o'quote")

    assert real_store.list_source_languages("general_knowledge") == {"store-live"}
    assert real_store.list_file_ids("jti_knowledge", "store-gone") == {"d.txt"}
