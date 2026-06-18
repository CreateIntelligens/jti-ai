"""Local backups for HCIoT images stored in MongoDB."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from app.services._shared.local_backup import safe_backup_filename, write_bytes_if_changed
from app.services.hciot.image_store import get_hciot_image_store

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = "/app/data/hciot/images"


def _extension_for(content_type: str | None) -> str:
    if content_type == "image/jpeg":
        return ".jpg"
    extension = mimetypes.guess_extension(content_type or "")
    return extension or ".bin"


def _filename_for(image_id: str, content_type: str | None) -> str:
    safe_id = safe_backup_filename(image_id.replace("/", "_"))
    return f"{safe_id}{_extension_for(content_type)}"


def backup_hciot_images(
    *,
    store: Any | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, int]:
    """Export MongoDB-backed HCIoT images to an ignored local backup directory."""
    image_store = store or get_hciot_image_store()
    target_dir = Path(output_dir or os.getenv("HCIOT_IMAGE_BACKUP_DIR", DEFAULT_BACKUP_DIR))
    target_dir.mkdir(parents=True, exist_ok=True)

    images = image_store.list_images()
    summary = {"total": len(images), "written": 0, "skipped": 0, "failed": 0}

    for image in images:
        image_id = image.get("image_id")
        if not image_id:
            summary["failed"] += 1
            continue

        try:
            full_image = image_store.get_image(image_id)
            data = full_image.get("data") if full_image else None
            if not isinstance(data, (bytes, bytearray)) or not data:
                summary["skipped"] += 1
                continue

            content_type = full_image.get("content_type") or image.get("content_type")
            target_path = target_dir / _filename_for(str(image_id), content_type)
            payload = bytes(data)
            if write_bytes_if_changed(target_path, payload) == "skipped":
                summary["skipped"] += 1
                continue

            summary["written"] += 1
        except Exception:
            logger.exception("Failed to back up HCIoT image %s", image_id)
            summary["failed"] += 1

    logger.info(
        "[HCIoT Images] Backup summary: total=%d written=%d skipped=%d failed=%d dir=%s",
        summary["total"],
        summary["written"],
        summary["skipped"],
        summary["failed"],
        target_dir,
    )
    return summary
