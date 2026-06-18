"""Local backups for HCIoT knowledge files stored in MongoDB."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.services._shared.local_backup import safe_backup_filename, write_bytes_if_changed, write_json_manifest
from app.services.hciot.knowledge_store import get_hciot_knowledge_store

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = "/app/data/hciot/knowledge"
DEFAULT_LANGUAGES = ("zh", "en")
MANIFEST_KEYS = (
    "filename",
    "display_name",
    "content_type",
    "size",
    "editable",
    "topic_id",
    "category_label",
    "topic_label",
    "created_at",
)


def _manifest_entry(metadata: dict[str, Any], backup_path: str) -> dict[str, Any]:
    entry = {key: metadata.get(key) for key in MANIFEST_KEYS if metadata.get(key) is not None}
    entry["backup_path"] = backup_path
    return entry


def _write_manifest(language_dir: Path, language: str, files: list[dict[str, Any]]) -> None:
    payload = {
        "language": language,
        "files": sorted(files, key=lambda item: item.get("filename", "")),
    }
    write_json_manifest(language_dir / "manifest.json", payload)


def backup_hciot_knowledge_files(
    *,
    store: Any | None = None,
    output_dir: str | Path | None = None,
    languages: tuple[str, ...] = DEFAULT_LANGUAGES,
) -> dict[str, int]:
    """Export MongoDB-backed HCIoT knowledge files to an ignored local directory."""
    knowledge_store = store or get_hciot_knowledge_store()
    target_dir = Path(output_dir or os.getenv("HCIOT_KNOWLEDGE_BACKUP_DIR", DEFAULT_BACKUP_DIR))

    summary = {"total": 0, "written": 0, "skipped": 0, "failed": 0}
    for language in languages:
        language_dir = target_dir / language
        files_dir = language_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        manifest_files: list[dict[str, Any]] = []

        for metadata in knowledge_store.list_files(language):
            summary["total"] += 1
            filename = metadata.get("filename") or metadata.get("name")
            if not filename:
                summary["failed"] += 1
                continue

            try:
                full_file = knowledge_store.get_file(language, filename)
                data = full_file.get("data") if full_file else None
                if not isinstance(data, (bytes, bytearray)) or not data:
                    summary["skipped"] += 1
                    continue

                safe_filename = safe_backup_filename(str(filename))
                backup_path = f"files/{safe_filename}"
                target_path = files_dir / safe_filename
                payload = bytes(data)
                if write_bytes_if_changed(target_path, payload) == "skipped":
                    summary["skipped"] += 1
                else:
                    summary["written"] += 1

                manifest_files.append(_manifest_entry({**metadata, **full_file}, backup_path))
            except Exception:
                logger.exception("Failed to back up HCIoT knowledge file %s/%s", language, filename)
                summary["failed"] += 1

        _write_manifest(language_dir, language, manifest_files)

    logger.info(
        "[HCIoT Knowledge] Backup summary: total=%d written=%d skipped=%d failed=%d dir=%s",
        summary["total"],
        summary["written"],
        summary["skipped"],
        summary["failed"],
        target_dir,
    )
    return summary
