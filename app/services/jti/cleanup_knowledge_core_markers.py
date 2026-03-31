"""
One-off cleanup for legacy [CORE: ...] markers inside JTI knowledge files.

Default mode is dry-run. Use --apply to persist updates to MongoDB.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from app.routers.knowledge_utils import (
    TEXT_PREVIEW_EXTENSIONS,
    extract_docx_text,
    write_docx_text,
)
from app.services.agent_utils import strip_core_markup
from app.services.knowledge_store import get_knowledge_store


def _iter_jti_knowledge_docs(store) -> list[dict[str, Any]]:
    return list(
        store.collection.find(
            {
                "$or": [
                    {"namespace": "jti"},
                    {"namespace": {"$exists": False}},
                ]
            },
            {
                "_id": 0,
                "filename": 1,
                "language": 1,
                "namespace": 1,
                "data": 1,
            },
        )
    )


def _normalize_file_content(filename: str, data: bytes) -> tuple[str | None, bytes | None]:
    ext = Path(filename).suffix.lower()

    if ext == ".docx":
        text = extract_docx_text(data)
        if text.startswith("[無法解析 docx:"):
            return None, None
        normalized = strip_core_markup(text)
        if normalized == text:
            return None, None
        return normalized, write_docx_text(data, normalized)

    if ext not in TEXT_PREVIEW_EXTENSIONS:
        return None, None

    text = data.decode("utf-8", errors="replace")
    normalized = strip_core_markup(text)
    if normalized == text:
        return None, None
    return normalized, normalized.encode("utf-8")


def cleanup_knowledge_core_markers(
    dry_run: bool = True,
    *,
    store=None,
) -> dict[str, int]:
    store = store or get_knowledge_store()

    summary = {
        "scanned": 0,
        "updated": 0,
        "skipped": 0,
    }

    for doc in _iter_jti_knowledge_docs(store):
        filename = doc.get("filename") or ""
        language = doc.get("language") or "zh"
        namespace = doc.get("namespace") or "jti"
        data = doc.get("data") or b""

        summary["scanned"] += 1
        normalized_text, normalized_bytes = _normalize_file_content(filename, data)

        if normalized_bytes is None:
            summary["skipped"] += 1
            continue

        if dry_run:
            print(f"[Dry Run] would update {namespace}/{language}/{filename}")
        else:
            store.update_file_content(language, filename, normalized_bytes, namespace=namespace)
            print(f"[Apply] updated {namespace}/{language}/{filename}")

        summary["updated"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean [CORE: ...] markers from JTI knowledge files")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist cleaned content to MongoDB. Default is dry-run.",
    )
    args = parser.parse_args()

    summary = cleanup_knowledge_core_markers(dry_run=not args.apply)
    mode = "apply" if args.apply else "dry-run"
    print(
        f"[Cleanup:{mode}] scanned={summary['scanned']} "
        f"updated={summary['updated']} skipped={summary['skipped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
