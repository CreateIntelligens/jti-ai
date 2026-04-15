"""
Seed quiz bank and quiz results from JSON into MongoDB.

Called during startup from deps.init_managers().
Synchronizes the default quiz bank when JSON and MongoDB drift apart.
Handles upgrade from legacy (no bank_id) → multi-set (bank_id).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.services.jti.quiz_bank_store import DEFAULT_BANK_ID
from app.services.jti.quiz_results_store import DEFAULT_SET_ID

logger = logging.getLogger(__name__)

QUIZ_BANK_PATHS = {
    "zh": Path("data/quiz_bank_color_zh.json"),
    "en": Path("data/quiz_bank_color_en.json"),
}

QUIZ_RESULTS_PATHS = {
    "zh": Path("data/quiz_results.json"),
    "en": Path("data/quiz_results_en.json"),
}


def _upgrade_legacy_data() -> None:
    """
    Upgrade legacy documents that lack bank_id.

    Strategy:
    - If a doc with bank_id="default" already exists, delete the legacy (no bank_id) duplicate.
    - Otherwise, update the legacy doc in-place to add bank_id.
    """
    from app.services.mongo_client import get_mongo_db

    db = get_mongo_db("jti_app")
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


def _default_bank_seed_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "預設題庫",
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "total_questions": data.get("total_questions", 4),
        "dimensions": data.get("dimensions", []),
        "tie_breaker_priority": data.get("tie_breaker_priority", []),
        "selection_rules": data.get("selection_rules", {}),
        "is_active": True,
        "is_default": True,
    }


def _default_bank_is_outdated(
    existing_meta: dict[str, Any] | None,
    existing_questions: list[dict[str, Any]],
    seed_data: dict[str, Any],
) -> bool:
    if not existing_meta:
        return True

    expected_meta = _default_bank_seed_payload(seed_data)
    for key in (
        "title",
        "description",
        "total_questions",
        "dimensions",
        "tie_breaker_priority",
        "selection_rules",
    ):
        if existing_meta.get(key) != expected_meta.get(key):
            return True

    expected_questions = seed_data.get("questions", [])
    return existing_questions != expected_questions


def _default_quiz_results_set_payload(language: str) -> dict[str, Any]:
    name = "預設測驗結果" if language == "zh" else "Default Quiz Results"
    return {
        "name": name,
        "is_active": True,
        "is_default": True,
    }


def _default_quiz_results_are_outdated(
    existing_meta: dict[str, Any] | None,
    existing_results: dict[str, dict[str, Any]],
    seed_data: dict[str, dict[str, Any]],
    language: str,
) -> bool:
    if not existing_meta:
        return True

    expected_meta = _default_quiz_results_set_payload(language)
    for key in ("name", "is_active", "is_default"):
        if existing_meta.get(key) != expected_meta.get(key):
            return True

    return existing_results != seed_data


def migrate_quiz_bank() -> None:
    """Seed quiz bank from JSON → MongoDB and sync stale default banks."""
    from app.services.jti.quiz_bank_store import get_quiz_bank_store

    # First, upgrade any legacy data
    _upgrade_legacy_data()

    store = get_quiz_bank_store()

    for lang, path in QUIZ_BANK_PATHS.items():
        if not path.exists():
            logger.info("[Startup] Quiz bank JSON not found for %s: %s", lang, path)
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        existing_meta = store.get_metadata(lang, bank_id=DEFAULT_BANK_ID)
        existing_questions = store.list_questions(lang, DEFAULT_BANK_ID)
        if not _default_bank_is_outdated(existing_meta, existing_questions, data):
            logger.debug("Quiz bank (%s) up to date, skipping", lang)
            continue

        # Upsert metadata with multi-set fields
        store.upsert_metadata(lang, DEFAULT_BANK_ID, _default_bank_seed_payload(data))

        # Replace all questions so stale extras are removed during sync.
        questions = data.get("questions", [])
        count = store.replace_all_questions(lang, DEFAULT_BANK_ID, questions)
        logger.info("[Startup] Synced quiz bank (%s): %d questions", lang, count)


def _upgrade_legacy_quiz_results() -> None:
    """
    Upgrade legacy quiz_results documents that lack set_id.

    Strategy:
    - If a doc with set_id="default" already exists for this quiz_id, delete the legacy duplicate.
    - Otherwise, update the legacy doc in-place to add set_id="default".
    Also ensure default set metadata exists.
    """
    from app.services.mongo_client import get_mongo_db

    db = get_mongo_db("jti_app")
    if db is None:
        return

    col = db["quiz_results"]
    legacy_docs = list(col.find({"set_id": {"$exists": False}}))
    for doc in legacy_docs:
        lang = doc.get("language")
        quiz_id = doc.get("quiz_id")
        existing = col.find_one({"language": lang, "set_id": DEFAULT_SET_ID, "quiz_id": quiz_id})
        if existing:
            col.delete_one({"_id": doc["_id"]})
        else:
            col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"set_id": DEFAULT_SET_ID}},
            )
    if legacy_docs:
        logger.info("[Startup] Processed %d legacy quiz result docs", len(legacy_docs))

    # Ensure default set metadata exists
    meta_col = db["quiz_results_metadata"]
    for lang in ["zh", "en"]:
        existing_meta = meta_col.find_one({"language": lang, "set_id": DEFAULT_SET_ID})
        if not existing_meta:
            now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            meta_col.insert_one({
                "language": lang,
                "set_id": DEFAULT_SET_ID,
                "name": _default_quiz_results_set_payload(lang)["name"],
                "is_active": True,
                "is_default": True,
                "created_at": now,
                "updated_at": now,
            })
            logger.info("[Startup] Created default quiz results metadata for %s", lang)


def migrate_quiz_results() -> None:
    """Seed quiz results from JSON → MongoDB and sync stale default sets."""
    from app.services.jti.quiz_results_store import get_quiz_results_store

    # First, upgrade any legacy data
    _upgrade_legacy_quiz_results()

    store = get_quiz_results_store()

    for lang, path in QUIZ_RESULTS_PATHS.items():
        if not path.exists():
            logger.info("[Startup] Quiz results JSON not found for %s: %s", lang, path)
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        existing_meta = store.get_set_metadata(lang, DEFAULT_SET_ID)
        existing_results = store.get_all_results(lang, set_id=DEFAULT_SET_ID)
        if not _default_quiz_results_are_outdated(existing_meta, existing_results, data, lang):
            logger.debug("Quiz results (%s) up to date, skipping", lang)
            continue

        store.upsert_set_metadata(lang, DEFAULT_SET_ID, _default_quiz_results_set_payload(lang))
        count = store.replace_all_results(lang, data, set_id=DEFAULT_SET_ID)
        logger.info("[Startup] Synced quiz results (%s): %d entries", lang, count)
