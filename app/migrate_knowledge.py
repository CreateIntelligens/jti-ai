"""
Migrate local knowledge files to MongoDB.

Usage:
    python -m app.migrate_knowledge
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from app.services.knowledge_store import get_knowledge_store

EDITABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".docx"}


def migrate_knowledge() -> int:
    root = Path(os.getenv("KB_ROOT", "data/knowledge"))
    store = get_knowledge_store()
    languages = ("zh", "en")

    if not root.exists():
        print(f"[Migrate] source directory not found: {root}")
        return 1

    total_files = 0
    migrated_files = 0

    print(f"[Migrate] source root: {root.resolve()}")

    for language in languages:
        lang_dir = root / language
        if not lang_dir.exists():
            print(f"[Migrate] skip language={language}: dir not found")
            continue

        print(f"[Migrate] language={language}")
        for file_path in sorted(lang_dir.iterdir()):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            total_files += 1
            data = file_path.read_bytes()
            ext = file_path.suffix.lower()
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            editable = ext in EDITABLE_EXTENSIONS

            meta = store.save_file(
                language=language,
                filename=file_path.name,
                data=data,
                display_name=file_path.name,
                content_type=content_type,
                editable=editable,
            )
            migrated_files += 1
            print(
                f"  - upserted: {meta['filename']} "
                f"(size={meta['size']}, editable={meta['editable']})"
            )

    print(f"[Migrate] done: {migrated_files}/{total_files} files migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(migrate_knowledge())
