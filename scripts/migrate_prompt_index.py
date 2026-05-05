#!/usr/bin/env python3
"""
One-time migration: move HCIoT/JTI prompts from shared prompts[] to app-specific index.

What it does:
1. For each HCIoT/JTI store doc, copies entries from prompts[] to {app}_prompt_index
2. Copies active_prompt_id to {app}_active_prompt_id
3. Clears prompts[] and active_prompt_id on those docs (so General starts clean)

Run inside the backend container:
    docker compose exec backend python scripts/migrate_prompt_index.py

Safe to run multiple times — skips docs that already have app-specific index.
"""

import os
import sys
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("ERROR: MONGODB_URI not set")
    sys.exit(1)

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
db = client["gemini_notebook"]
collection = db["prompts"]

# Store name -> (prompt_index_attr, active_prompt_id_attr)
APP_STORES = {
    "__hciot__": ("hciot_prompt_index", "hciot_active_prompt_id"),
    "__hciot__en": ("hciot_prompt_index", "hciot_active_prompt_id"),
    "__jti__": ("jti_prompt_index", "jti_active_prompt_id"),
    "__jti__en": ("jti_prompt_index", "jti_active_prompt_id"),
}


def build_index_entries(prompts: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "id": prompt.get("id", ""),
            "name": prompt.get("name", ""),
            "created_at": prompt.get("created_at", ""),
            "updated_at": prompt.get("updated_at", ""),
        }
        for prompt in prompts
    ]


def migrate_store(store_name: str, index_attr: str, active_attr: str) -> None:
    doc = collection.find_one({"store_name": store_name})
    if not doc:
        print(f"  [{store_name}] No doc found, skipping.")
        return

    existing_index = doc.get(index_attr)
    if existing_index:
        print(f"  [{store_name}] Already has {index_attr} ({len(existing_index)} entries), skipping.")
        return

    prompts = doc.get("prompts", [])
    active_id = doc.get("active_prompt_id")
    if not prompts and not active_id:
        print(f"  [{store_name}] prompts[] empty and no active_prompt_id, nothing to migrate.")
        return

    index_entries = build_index_entries(prompts)
    print(f"  [{store_name}] Migrating {len(index_entries)} prompts → {index_attr}")
    if active_id:
        print(f"  [{store_name}] active_prompt_id '{active_id}' → {active_attr}")

    result = collection.update_one(
        {"store_name": store_name},
        {
            "$set": {
                index_attr: index_entries,
                active_attr: active_id,
                "prompts": [],
                "active_prompt_id": None,
            }
        },
    )
    print(f"  [{store_name}] Done (modified: {result.modified_count})")


def migrate() -> None:
    for store_name, (index_attr, active_attr) in APP_STORES.items():
        migrate_store(store_name, index_attr, active_attr)


if __name__ == "__main__":
    print("=== Prompt Index Migration ===")
    migrate()
    print("=== Done ===")
