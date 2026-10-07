"""Compare the local LanceDB index against the MongoDB knowledge stores.

Each host keeps its own LanceDB while all hosts share MongoDB, so the index of
every host should match the same source of truth. "Clean" means: the table
belongs to the configured embedding model, every live file is indexed with its
current content, nothing is left over from deleted files or stores, and no
chunk is stored twice.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.services.embedding.service import configured_dimensions
from app.services.rag.backfill import _knowledge_source_type, get_backfill_service
from app.services.vector_store.lancedb import knowledge_table_name

_ROW_LIMIT = 1_000_000


def audit_rag_index(jobs: list[tuple[str, str]]) -> dict[str, Any]:
    """jobs: the (source_type, partition) pairs backfill is responsible for."""
    backfill = get_backfill_service()
    store = backfill.lancedb_store
    table = store.table
    report: dict[str, Any] = {
        "table": store.table_name,
        "expected_table": knowledge_table_name(),
        "dimensions": None,
        "expected_dimensions": configured_dimensions(),
        "other_tables": [],
        "total_chunks": 0,
        "partitions": {},
        "orphan_partitions": {},
        "duplicate_chunks": 0,
    }
    try:
        report["other_tables"] = sorted(
            name for name in store._get_db().list_tables().tables
            if name != store.table_name
        )
    except Exception:
        pass

    rows: list[dict[str, Any]] = []
    if table is not None:
        report["dimensions"] = table.schema.field("vector").type.list_size
        rows = (
            table.search()
            .select(["file_id", "source_type", "source_language", "chunk_index", "file_fingerprint"])
            .limit(_ROW_LIMIT)
            .to_list()
        )
    report["total_chunks"] = len(rows)

    by_partition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_partition[(row["source_type"], row["source_language"])].append(row)

    chunk_keys = Counter(
        (r["source_type"], r["source_language"], r["file_id"], r["chunk_index"]) for r in rows
    )
    report["duplicate_chunks"] = sum(n - 1 for n in chunk_keys.values() if n > 1)

    expected_partitions = set()
    for source_type, partition in jobs:
        key = (_knowledge_source_type(source_type), partition)
        expected_partitions.add(key)
        report["partitions"][f"{key[0]}/{partition}"] = _audit_partition(
            backfill, source_type, partition, by_partition.get(key, [])
        )

    for key, part_rows in by_partition.items():
        if key not in expected_partitions:
            report["orphan_partitions"][f"{key[0]}/{key[1]}"] = len(part_rows)

    report["clean"] = (
        report["table"] == report["expected_table"]
        and report["dimensions"] == report["expected_dimensions"]
        and not report["orphan_partitions"]
        and report["duplicate_chunks"] == 0
        and all(
            not (p["missing"] or p["stale"] or p["orphans"])
            for p in report["partitions"].values()
        )
    )
    return report


def _audit_partition(
    backfill: Any,
    source_type: str,
    partition: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    indexed: dict[str, str] = {}
    for row in rows:
        indexed[row["file_id"]] = row.get("file_fingerprint") or ""

    live: dict[str, str] = {}
    for filename, _display, data, _info in backfill._get_files_and_data(source_type, partition):
        # 抽不出文字的檔案 backfill 本來就不會寫入，不算缺漏。
        if backfill._extract_file_text(filename, data):
            live[filename] = backfill._compute_fingerprint(data)

    return {
        "files": len(live),
        "chunks": len(rows),
        "missing": sorted(set(live) - set(indexed)),
        "stale": sorted(f for f in live if f in indexed and indexed[f] != live[f]),
        "orphans": sorted(set(indexed) - set(live)),
    }
