"""Flatten bilingual labels on hciot_app.knowledge_files.

For each doc, set `topic_label` and `category_label` from the doc's own
language partition (`topic_label_<lang>` / `category_label_<lang>`),
then drop the four legacy bilingual fields.

Run inside the backend environment:
    python scripts/migrate_flatten_knowledge_labels.py
"""

import os

from pymongo import MongoClient


MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise SystemExit("ERROR: MONGODB_URI not set")

LEGACY_FIELDS = (
    "topic_label_zh",
    "topic_label_en",
    "category_label_zh",
    "category_label_en",
)


def main() -> None:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    collection = client["hciot_app"]["knowledge_files"]

    cursor = collection.find(
        {"namespace": "hciot"},
        {"_id": 1, "language": 1, **{field: 1 for field in LEGACY_FIELDS}},
    )

    flattened = 0
    skipped = 0
    for doc in cursor:
        lang = doc.get("language") or "zh"
        topic_label = doc.get(f"topic_label_{lang}")
        category_label = doc.get(f"category_label_{lang}")

        update = {
            "$set": {
                "topic_label": topic_label,
                "category_label": category_label,
            },
            "$unset": {field: "" for field in LEGACY_FIELDS},
        }
        result = collection.update_one({"_id": doc["_id"]}, update)
        if result.modified_count:
            flattened += 1
        else:
            skipped += 1

    print(f"flattened={flattened} skipped={skipped}")


if __name__ == "__main__":
    main()
