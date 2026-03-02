"""
Seed quiz bank and color results from JSON into MongoDB.

Called during startup from deps.init_managers().
Skips if data already exists in MongoDB.
Handles upgrade from legacy (no bank_id) → multi-set (bank_id).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.quiz_bank_store import DEFAULT_BANK_ID

logger = logging.getLogger(__name__)

QUIZ_BANK_PATHS = {
    "zh": Path("data/quiz_bank_color_zh.json"),
    "en": Path("data/quiz_bank_color_en.json"),
}

COLOR_RESULTS_PATH = Path("data/color_results.json")


def _upgrade_legacy_data() -> None:
    """
    Upgrade legacy documents that lack bank_id.

    Strategy:
    - If a doc with bank_id="default" already exists, delete the legacy (no bank_id) duplicate.
    - Otherwise, update the legacy doc in-place to add bank_id.
    """
    from app.services.mongo_client import get_mongo_db

    db = get_mongo_db()
    if db is None:
        return

    # --- Metadata ---
    meta_col = db["quiz_bank_metadata"]
    legacy_meta = list(meta_col.find({"bank_id": {"$exists": False}}))
    for doc in legacy_meta:
        lang = doc.get("language")
        existing_default = meta_col.find_one({"language": lang, "bank_id": DEFAULT_BANK_ID})
        if existing_default:
            meta_col.delete_one({"_id": doc["_id"]})
            logger.info("[Startup] Removed legacy metadata for %s", lang)
        else:
            meta_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "bank_id": DEFAULT_BANK_ID,
                    "name": "預設題庫",
                    "is_active": True,
                    "is_default": True,
                }},
            )
            logger.info("[Startup] Upgraded legacy metadata for %s", lang)

    # --- Questions ---
    q_col = db["quiz_bank_questions"]
    legacy_questions = list(q_col.find({"bank_id": {"$exists": False}}))
    for doc in legacy_questions:
        lang = doc.get("language")
        q_id = doc.get("id")
        # Check if a proper default-bank question with this id already exists
        existing = q_col.find_one({"language": lang, "bank_id": DEFAULT_BANK_ID, "id": q_id})
        if existing:
            # Delete the legacy duplicate
            q_col.delete_one({"_id": doc["_id"]})
        else:
            # Upgrade in-place
            q_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"bank_id": DEFAULT_BANK_ID}},
            )
    if legacy_questions:
        logger.info("[Startup] Processed %d legacy questions", len(legacy_questions))

def migrate_quiz_bank() -> None:
    """Seed quiz bank from JSON → MongoDB (skip if already populated)."""
    from app.services.quiz_bank_store import get_quiz_bank_store

    # First, upgrade any legacy data
    _upgrade_legacy_data()

    store = get_quiz_bank_store()

    for lang, path in QUIZ_BANK_PATHS.items():
        if not path.exists():
            logger.info("[Startup] Quiz bank JSON not found for %s: %s", lang, path)
            continue

        # Check if default bank already exists (either fresh or upgraded)
        existing = store.get_metadata(lang, bank_id=DEFAULT_BANK_ID)
        if existing:
            logger.info("[Startup] Quiz bank (%s) already in MongoDB, skipping seed", lang)
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Upsert metadata with multi-set fields
        store.upsert_metadata(lang, DEFAULT_BANK_ID, {
            "quiz_id": data.get("quiz_id", ""),
            "name": "預設題庫",
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "total_questions": data.get("total_questions", 5),
            "dimensions": data.get("dimensions", []),
            "tie_breaker_priority": data.get("tie_breaker_priority", []),
            "selection_rules": data.get("selection_rules", {}),
            "is_active": True,
            "is_default": True,
        })

        # Bulk insert questions
        questions = data.get("questions", [])
        count = store.bulk_upsert_questions(lang, DEFAULT_BANK_ID, questions)
        print(f"[Startup] ✅ Seeded quiz bank ({lang}): {count} questions")


def migrate_color_results() -> None:
    """Seed color results from JSON → MongoDB (skip if already populated)."""
    from app.services.color_results_store import get_color_results_store

    store = get_color_results_store()

    for lang in ["zh"]:  # 先中文，未來加 en
        existing = store.list_results(lang)
        if existing:
            logger.info("[Startup] Color results (%s) already in MongoDB, skipping seed", lang)
            continue

        if not COLOR_RESULTS_PATH.exists():
            logger.info("[Startup] Color results JSON not found: %s", COLOR_RESULTS_PATH)
            continue

        with open(COLOR_RESULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = store.bulk_upsert_results(lang, data)
        print(f"[Startup] ✅ Seeded color results ({lang}): {count} entries")
