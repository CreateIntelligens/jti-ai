"""Shared helpers for writing ignored local backups from DB-backed stores."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

WriteStatus = Literal["written", "skipped"]


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def safe_backup_filename(filename: str) -> str:
    return Path(filename.replace("\\", "_").replace("\x00", "")).name


def write_bytes_if_changed(target_path: Path, payload: bytes) -> WriteStatus:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and target_path.read_bytes() == payload:
        return "skipped"
    target_path.write_bytes(payload)
    return "written"


def write_json_manifest(target_path: Path, payload: dict[str, Any]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n"
    )
