#!/usr/bin/env python3
"""
MongoDB Migration: color → quiz rename

Renames collections and fields:
1. color_results → quiz_results  (collection rename)
2. color_results_metadata → quiz_results_metadata  (collection rename)
3. quiz_results: field color_id → quiz_id
4. sessions: fields color_result_id → quiz_result_id, color_scores → quiz_scores, color_result → quiz_result
5. conversations: session_state.color_result_id → session_state.quiz_result_id

Idempotent: checks whether old collection/field exists before operating.
"""

import logging
import os
import sys

from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/jti_app")
DB_NAME = "jti_app"


def get_db():
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    logger.info("Connected to MongoDB")
    return client[DB_NAME]


# ---------------------------------------------------------------------------
# Step 1 & 2: Rename collections
# ---------------------------------------------------------------------------

def rename_collection(db, old_name: str, new_name: str) -> bool:
    """Rename a collection if the old one exists and the new one doesn't."""
    existing = db.list_collection_names()

    if new_name in existing and old_name not in existing:
        logger.info("Collection '%s' already exists (old '%s' gone) — skipping", new_name, old_name)
        return False

    if old_name not in existing:
        logger.info("Collection '%s' does not exist — skipping rename", old_name)
        return False

    if new_name in existing:
        # Both exist — merge old into new, then drop old
        logger.warning(
            "Both '%s' and '%s' exist. Merging old docs into new collection.",
            old_name, new_name,
        )
        old_docs = list(db[old_name].find())
        if old_docs:
            # Remove _id to avoid duplicate key errors; use insert with ordered=False
            for doc in old_docs:
                doc.pop("_id", None)
            try:
                db[new_name].insert_many(old_docs, ordered=False)
            except Exception as e:
                logger.warning("Some docs failed to merge (likely duplicates): %s", e)
        db[old_name].drop()
        logger.info("Merged '%s' into '%s' and dropped old collection", old_name, new_name)
        return True

    db[old_name].rename(new_name)
    logger.info("Renamed collection '%s' → '%s'", old_name, new_name)
    return True


# ---------------------------------------------------------------------------
# Step 3: Rename field color_id → quiz_id in quiz_results
# ---------------------------------------------------------------------------

def rename_quiz_results_fields(db) -> int:
    """Rename color_id → quiz_id in quiz_results collection."""
    col = db["quiz_results"]

    # Only update docs that still have the old field
    count = col.count_documents({"color_id": {"$exists": True}})
    if count == 0:
        logger.info("quiz_results: no documents with 'color_id' field — skipping")
        return 0

    result = col.update_many(
        {"color_id": {"$exists": True}},
        {"$rename": {"color_id": "quiz_id"}},
    )
    logger.info("quiz_results: renamed color_id → quiz_id in %d documents", result.modified_count)

    # Update indexes: drop old, create new
    _rebuild_quiz_results_indexes(col)

    return result.modified_count


def _rebuild_quiz_results_indexes(col):
    """Drop color_id-based indexes and create quiz_id-based ones."""
    try:
        # Drop any index that references color_id
        for idx_name, meta in list(col.index_information().items()):
            if idx_name == "_id_":
                continue
            key_fields = [k for k, _ in meta.get("key", [])]
            if "color_id" in key_fields:
                col.drop_index(idx_name)
                logger.info("quiz_results: dropped index '%s'", idx_name)
    except Exception as e:
        logger.warning("Failed to drop old indexes: %s", e)

    try:
        col.create_index(
            [("language", 1), ("set_id", 1), ("quiz_id", 1)],
            unique=True,
        )
        col.create_index("language")
        logger.info("quiz_results: created new indexes with quiz_id")
    except Exception as e:
        logger.warning("Failed to create new indexes: %s", e)


# ---------------------------------------------------------------------------
# Step 4: Rename fields in sessions collection
# ---------------------------------------------------------------------------

def rename_session_fields(db) -> int:
    """Rename color_result_id, color_scores, color_result in sessions."""
    col = db["sessions"]

    field_renames = {
        "color_result_id": "quiz_result_id",
        "color_scores": "quiz_scores",
        "color_result": "quiz_result",
    }

    total = 0
    for old_field, new_field in field_renames.items():
        count = col.count_documents({old_field: {"$exists": True}})
        if count == 0:
            logger.info("sessions: no documents with '%s' — skipping", old_field)
            continue

        result = col.update_many(
            {old_field: {"$exists": True}},
            {"$rename": {old_field: new_field}},
        )
        logger.info("sessions: renamed '%s' → '%s' in %d documents", old_field, new_field, result.modified_count)
        total += result.modified_count

    # Also rename fields inside session snapshots stored as nested docs
    # (sessions may have snapshot-like embedded data)
    return total


# ---------------------------------------------------------------------------
# Step 5: Rename fields in conversations (session_state)
# ---------------------------------------------------------------------------

def rename_conversation_fields(db) -> int:
    """Rename session_state.color_result_id → session_state.quiz_result_id in conversations."""
    col = db["conversations"]

    old_field = "session_state.color_result_id"
    new_field = "session_state.quiz_result_id"

    count = col.count_documents({old_field: {"$exists": True}})
    if count == 0:
        logger.info("conversations: no documents with '%s' — skipping", old_field)
        return 0

    result = col.update_many(
        {old_field: {"$exists": True}},
        {"$rename": {old_field: new_field}},
    )
    logger.info(
        "conversations: renamed '%s' → '%s' in %d documents",
        old_field, new_field, result.modified_count,
    )

    # Also rename session_snapshot fields (used by rebuild_session_from_logs)
    for old_snap, new_snap in [
        ("session_snapshot.color_result_id", "session_snapshot.quiz_result_id"),
        ("session_snapshot.color_scores", "session_snapshot.quiz_scores"),
        ("session_snapshot.color_result", "session_snapshot.quiz_result"),
    ]:
        snap_count = col.count_documents({old_snap: {"$exists": True}})
        if snap_count > 0:
            snap_result = col.update_many(
                {old_snap: {"$exists": True}},
                {"$rename": {old_snap: new_snap}},
            )
            logger.info(
                "conversations: renamed '%s' → '%s' in %d documents",
                old_snap, new_snap, snap_result.modified_count,
            )

    return result.modified_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def migrate(db=None):
    """Run all migration steps."""
    if db is None:
        db = get_db()

    logger.info("=" * 60)
    logger.info("Starting migration: color → quiz")
    logger.info("=" * 60)

    # Step 1: Rename color_results → quiz_results
    rename_collection(db, "color_results", "quiz_results")

    # Step 2: Rename color_results_metadata → quiz_results_metadata
    rename_collection(db, "color_results_metadata", "quiz_results_metadata")

    # Step 3: Rename fields in quiz_results
    rename_quiz_results_fields(db)

    # Step 4: Rename fields in sessions
    rename_session_fields(db)

    # Step 5: Rename fields in conversations
    rename_conversation_fields(db)

    logger.info("=" * 60)
    logger.info("Migration complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    migrate()
