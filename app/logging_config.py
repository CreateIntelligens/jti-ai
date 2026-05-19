"""File-based logging: per-module directories with daily rotation.

Routes log records into per-module directories based on the logger name
prefix:

    app.routers.jti.* / app.services.jti.* / app.tools.jti.*  -> jti
    app.routers.hciot.* / app.services.hciot.*                 -> hciot
    app.routers.general.* / app.services.general.*             -> general

Each module gets its own directory under ``logs/``:

    logs/{module}/app.log      INFO and above
    logs/{module}/error.log    ERROR and above

Records that do not belong to a known module are written under
``logs/shared/`` so cross-cutting services (Gemini clients, prompts,
Mongo, RAG, ...) are still captured and nothing is silently dropped.

Rotated files stay inside each module directory (``app.log.2026-05-17``).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(os.getenv("LOG_DIR", "/app/logs"))
_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "90"))
_LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Module key -> tuple of logger-name prefixes that map to it.
_MODULE_PREFIXES: dict[str, tuple[str, ...]] = {
    "jti": ("app.routers.jti", "app.services.jti", "app.tools.jti"),
    "hciot": ("app.routers.hciot", "app.services.hciot"),
    "general": ("app.routers.general", "app.services.general"),
}
_HANDLER_SPECS = (("app.log", logging.INFO), ("error.log", logging.ERROR))
# Cross-cutting / shared services that match no module land here.
_SHARED_MODULE = "shared"


def _module_for(logger_name: str) -> str:
    """Map a logger name to its owning module key (or shared)."""
    for module, prefixes in _MODULE_PREFIXES.items():
        for prefix in prefixes:
            if logger_name == prefix or logger_name.startswith(f"{prefix}."):
                return module
    return _SHARED_MODULE


class _ModuleFilter(logging.Filter):
    """Pass only records whose logger name belongs to ``module``."""

    def __init__(self, module: str) -> None:
        super().__init__()
        self._module = module

    def filter(self, record: logging.LogRecord) -> bool:
        return _module_for(record.name) == self._module


def _build_handler(path: Path, level: int, module: str) -> TimedRotatingFileHandler:
    handler = TimedRotatingFileHandler(
        path,
        when="midnight",
        backupCount=_RETENTION_DAYS,
        encoding="utf-8",
        utc=False,
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_ModuleFilter(module))
    return handler


def configure_file_logging() -> None:
    """Attach per-module file handlers to the root logger.

    Idempotent: re-invocation will not duplicate handlers. Safe to call
    from both the uvicorn parent and its ``--reload`` worker subprocess —
    whichever process handles requests gets the handlers attached.
    """
    root = logging.getLogger()

    if any(getattr(h, "_jtai_file_handler", False) for h in root.handlers):
        return

    for module in (*_MODULE_PREFIXES.keys(), _SHARED_MODULE):
        module_dir = _LOG_DIR / module
        module_dir.mkdir(parents=True, exist_ok=True)

        for filename, level in _HANDLER_SPECS:
            handler = _build_handler(module_dir / filename, level, module)
            setattr(handler, "_jtai_file_handler", True)
            root.addHandler(handler)
