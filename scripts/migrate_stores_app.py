"""Migrate existing dynamic stores to include the managed_app field.

Run inside the backend environment:
    python scripts/migrate_stores_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Allow importing app modules when the script is run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.general.stores import StoreRegistry
from app.services import app_key_map, gemini_clients


def main() -> None:
    load_dotenv()
    # Initialize the Gemini key registry so that key indexes can be mapped to key names.
    gemini_clients.init_registry()

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        collection = client["jti_app"][StoreRegistry.COLLECTION_NAME]
    except PyMongoError as exc:
        print(f"MongoDB connection failed: {exc}")
        sys.exit(1)

    print("Starting migration of dynamic stores...")
    cursor = collection.find({})

    updated_count = 0
    skipped_count = 0

    for doc in cursor:
        doc_id = doc["_id"]
        name = doc.get("name")
        key_index = doc.get("key_index")
        existing_app = doc.get("managed_app")

        target_app = (
            app_key_map.resolve_app_for_key_index(key_index)
            if isinstance(key_index, int)
            else "general"
        )

        if existing_app == target_app:
            skipped_count += 1
            continue

        result = collection.update_one(
            {"_id": doc_id},
            {"$set": {"managed_app": target_app}},
        )
        if result.modified_count:
            print(f"Updated store '{name}' (key_index={key_index}): managed_app={existing_app} -> {target_app}")
            updated_count += 1
        else:
            skipped_count += 1

    print(f"Migration completed. Updated: {updated_count}, Skipped: {skipped_count}")


if __name__ == "__main__":
    main()
