"""Build the RAG index for the configured embedding model ahead of a cutover.

The LanceDB table is named after the embedding model, so the new model's
table can be filled while the running backend keeps serving from the old
one. Point the EMBEDDING_* variables at the new model when you run it:

    docker compose exec -u appuser \\
        -e EMBEDDING_SERVICE_URL=http://<new embedding>:8009 \\
        -e EMBEDDING_EXPECTED_MODEL=google/embeddinggemma-2 \\
        -e EMBEDDING_EXPECTED_DIMENSION=768 \\
        backend python scripts/prebuild_rag_index.py

Unchanged files are skipped by fingerprint, so re-running only fills gaps.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import _build_rag_backfill_jobs, _list_general_store_names
from app.services.rag.backfill import get_backfill_service
from app.services.vector_store.lancedb import knowledge_table_name


class _ErrorCollector(logging.Handler):
    """run_backfill 對單檔失敗只寫 log 不拋例外；收集起來，避免帶著半套索引去切換。"""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    errors = _ErrorCollector()
    logging.getLogger("app.services").addHandler(errors)
    backfill = get_backfill_service()
    service = backfill.embedding_service
    print(f"table:    {knowledge_table_name()}")
    print(f"service:  {service.service_url}")
    print(f"identity: {service._identity('document')}")

    # 先打一次，模型還在下載或載入時在這裡失敗，不會留下半套索引。
    service.encode("warmup")

    for source_type, partition in _build_rag_backfill_jobs(
        _list_general_store_names()
    ):
        backfill.run_backfill(source_type, partition)
        print(f"indexed:  {source_type}/{partition}")

    stats = backfill.lancedb_store.get_stats()
    print(f"chunks:   {stats['count']} in {stats['table_name']}")
    if errors.messages:
        print(f"FAILED:   {len(errors.messages)} error(s); fix and re-run")
        for message in errors.messages[:20]:
            print(f"  - {message}")
        return 1
    return 0 if stats["count"] else 1


if __name__ == "__main__":
    sys.exit(main())
