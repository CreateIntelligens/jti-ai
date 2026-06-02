"""APP_KEY_MAP parsing and app-level Gemini key resolution."""

from __future__ import annotations

import logging
import os

from app.services import gemini_clients

logger = logging.getLogger(__name__)


def load_app_key_map() -> dict[str, str]:
    """Load APP_KEY_MAP as {app: key_name}.

    APP_KEY_MAP format: app:key_name,app2:key_name2. Invalid entries are skipped
    so a single bad token does not prevent the app from starting.
    """
    mapping: dict[str, str] = {}
    raw = os.getenv("APP_KEY_MAP", "")
    for token in raw.split(","):
        entry = token.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.warning("Invalid APP_KEY_MAP entry %r: expected app:key_name", entry)
            continue
        app, key_name = entry.split(":", 1)
        app = app.strip().lower()
        key_name = key_name.strip()
        if not app or not key_name:
            logger.warning("Invalid APP_KEY_MAP entry %r: app and key_name are required", entry)
            continue
        mapping[app] = key_name
    return mapping


def resolve_key_index_for_app(app: str) -> int:
    """Resolve a managed app name to a Gemini key index, returning -1 if missing."""
    normalized_app = (app or "").strip().lower()
    if not normalized_app:
        return -1

    key_name = load_app_key_map().get(normalized_app)
    if not key_name:
        return -1
    return gemini_clients.resolve_key_index_by_name(key_name)


def resolve_app_for_key_index(key_index: int) -> str:
    """Resolve a Gemini key index to a managed app name, defaulting to general."""
    if key_index < 0:
        return "general"
    for app, key_name in load_app_key_map().items():
        if gemini_clients.resolve_key_index_by_name(key_name) == key_index:
            return app
    return "general"


def resolve_app_for_key_name(name: str) -> str:
    """Resolve a Gemini key display name to a managed app name, defaulting to general."""
    target = (name or "").strip().lower()
    if not target:
        return "general"
    for app, key_name in load_app_key_map().items():
        if key_name.strip().lower() == target:
            return app
    return "general"


def validate_app_key_map() -> list[tuple[str, str]]:
    """Log APP_KEY_MAP entries that do not resolve to a configured Gemini key."""
    missing: list[tuple[str, str]] = []
    for app, key_name in load_app_key_map().items():
        if gemini_clients.resolve_key_index_by_name(key_name) < 0:
            missing.append((app, key_name))

    if missing:
        details = ", ".join(f"{app}:{key_name}" for app, key_name in missing)
        logger.error(
            "APP_KEY_MAP references Gemini key names that do not exist in GEMINI_API_KEYS: %s",
            details,
        )
    return missing
