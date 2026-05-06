"""Backfill language='zh' on legacy HCIoT topic documents.

Run inside the backend environment:
    python scripts/migrate_hciot_topic_language.py
"""

import os

from pymongo import MongoClient


MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise SystemExit("ERROR: MONGODB_URI not set")


def main() -> None:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    collection = client["hciot_app"]["hciot_topics"]
    result = collection.update_many(
        {"language": {"$exists": False}},
        {"$set": {"language": "zh"}},
    )
    print(f"matched={result.matched_count} modified={result.modified_count}")


if __name__ == "__main__":
    main()
