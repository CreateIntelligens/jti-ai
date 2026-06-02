"""Report APP_KEY_MAP resolution and dynamic store key bindings.

Run inside the backend container:
    python scripts/check_app_key_map.py

This script is read-only: it initializes the in-memory Gemini key registry and
queries MongoDB without creating indexes or updating documents.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Allow importing app modules when the script is run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.general.stores import StoreRegistry
from app.services import app_key_map, gemini_clients


def _key_name_for_index(key_index: Any, key_names: list[str]) -> str:
    if isinstance(key_index, int) and 0 <= key_index < len(key_names):
        return key_names[key_index]
    return ""


def _load_dynamic_stores() -> list[dict[str, Any]]:
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        collection = client["jti_app"][StoreRegistry.COLLECTION_NAME]
        docs = collection.find(
            {},
            {
                "_id": 0,
                "name": 1,
                "display_name": 1,
                "key_index": 1,
                "managed_app": 1,
                "owner_key_hash": 1,
                "created_at": 1,
            },
        ).sort("created_at", 1)
        return list(docs)
    except PyMongoError as exc:
        print(f"Dynamic store scan unavailable: {exc}")
        return []


def _print_app_mapping(key_names: list[str]) -> dict[str, int]:
    mapping = app_key_map.load_app_key_map()
    expected_indexes: dict[str, int] = {}

    print("APP_KEY_MAP")
    if not mapping:
        print("  (empty)")
        return expected_indexes

    for app, mapped_key_name in mapping.items():
        index = gemini_clients.resolve_key_index_by_name(mapped_key_name)
        expected_indexes[app] = index
        actual_name = _key_name_for_index(index, key_names)
        status = "OK" if index >= 0 else "MISSING"
        print(
            f"  {app} -> {mapped_key_name} -> "
            f"index={index if index >= 0 else 'missing'} name={actual_name or '-'} [{status}]"
        )
    return expected_indexes


def _print_dynamic_stores(key_names: list[str], expected_indexes: dict[str, int]) -> None:
    print("\nDynamic stores")
    stores = _load_dynamic_stores()
    if not stores:
        print("  (none)")
        return

    for store in stores:
        name = store.get("name") or "-"
        display_name = store.get("display_name") or name
        key_index = store.get("key_index")
        key_name = _key_name_for_index(key_index, key_names)
        managed_app = (store.get("managed_app") or "").strip().lower()
        owner_bound = bool(store.get("owner_key_hash"))

        if owner_bound and key_index is None:
            status = "USER_KEY"
        elif not isinstance(key_index, int):
            status = "NO_KEY_INDEX"
        elif not key_name:
            status = "INVALID_INDEX"
        elif managed_app and managed_app in expected_indexes and key_index != expected_indexes[managed_app]:
            status = f"MISMATCH expected_index={expected_indexes[managed_app]}"
        else:
            status = "OK"

        app_suffix = f" app={managed_app}" if managed_app else ""
        print(
            f"  {name} ({display_name}){app_suffix} -> "
            f"key_index={key_index} name={key_name or '-'} [{status}]"
        )


def main() -> None:
    gemini_clients.init_registry()
    key_names = gemini_clients.get_key_names()
    print(f"Gemini registry: {len(key_names)} key(s)")
    expected_indexes = _print_app_mapping(key_names)
    _print_dynamic_stores(key_names, expected_indexes)


if __name__ == "__main__":
    main()
