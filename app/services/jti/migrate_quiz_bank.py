"""
Seed quiz bank and quiz results from JSON into MongoDB.

Called during startup from deps.init_managers().
Synchronizes the default quiz bank when JSON and MongoDB drift apart.
Handles upgrade from legacy (no bank_id) → multi-set (bank_id).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.jti.quiz_bank_store import DEFAULT_BANK_ID
from app.services.jti.quiz_results_store import DEFAULT_SET_ID

from app.services.quiz.config import JTI_STORE_NAME

logger = logging.getLogger(__name__)

QUIZ_BANK_PATHS = {
    "zh": Path("data/quiz_bank_color_zh.json"),
    "en": Path("data/quiz_bank_color_en.json"),
}

QUIZ_RESULTS_PATHS = {
    "zh": Path("data/quiz_results.json"),
    "en": Path("data/quiz_results_en.json"),
}


_backfill_done = False


def _backfill_store_name(db) -> None:
    """Backfill store_name=__jti__ for existing data and drop old unique indexes.

    Idempotent: both migrate_quiz_bank() and migrate_quiz_results() run at startup
    and each invoke this, so guard against doing the (otherwise no-op) full-collection
    scans twice in a single process.
    """
    global _backfill_done
    if db is None or _backfill_done:
        return
    _backfill_done = True

    # 1. Backfill quiz_bank_metadata
    meta_col = db["quiz_bank_metadata"]
    meta_col.update_many({"store_name": {"$exists": False}}, {"$set": {"store_name": JTI_STORE_NAME}})

    # Drop old index
    try:
        meta_col.drop_index("language_1_bank_id_1")
        logger.info("[Startup] Dropped old quiz_bank_metadata index language_1_bank_id_1")
    except Exception:
        pass

    # 2. Backfill quiz_bank_questions
    q_col = db["quiz_bank_questions"]
    q_col.update_many({"store_name": {"$exists": False}}, {"$set": {"store_name": JTI_STORE_NAME}})

    # 3. Backfill quiz_results_metadata
    res_meta_col = db["quiz_results_metadata"]
    res_meta_col.update_many({"store_name": {"$exists": False}}, {"$set": {"store_name": JTI_STORE_NAME}})

    # Drop old index
    try:
        res_meta_col.drop_index("uniq_language_set_id")
        logger.info("[Startup] Dropped old quiz_results_metadata index uniq_language_set_id")
    except Exception:
        pass

    # 4. Backfill quiz_results
    res_col = db["quiz_results"]
    res_col.update_many({"store_name": {"$exists": False}}, {"$set": {"store_name": JTI_STORE_NAME}})


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

    # Backfill store_name first
    _backfill_store_name(db)

    # --- Metadata ---
    meta_col = db["quiz_bank_metadata"]
    legacy_meta = list(meta_col.find({"bank_id": {"$exists": False}}))
    for doc in legacy_meta:
        lang = doc.get("language")
        store_name = doc.get("store_name", JTI_STORE_NAME)
        existing_default = meta_col.find_one({"store_name": store_name, "language": lang, "bank_id": DEFAULT_BANK_ID})
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
        store_name = doc.get("store_name", JTI_STORE_NAME)
        # Check if a proper default-bank question with this id already exists
        existing = q_col.find_one({"store_name": store_name, "language": lang, "bank_id": DEFAULT_BANK_ID, "id": q_id})
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
    """Default bank 的「內容」欄位 (JSON 同步用)。

    不含 is_active: active 是執行期狀態,只在首次播種時補上 default。
    之後 JSON 同步只更新內容欄位,避免覆寫使用者已啟用的自訂 bank。
    """
    return {
        "name": "預設題庫",
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "total_questions": data.get("total_questions", 4),
        "dimensions": data.get("dimensions", []),
        "tie_breaker_priority": data.get("tie_breaker_priority", []),
        "selection_rules": data.get("selection_rules", {}),
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
    # First, upgrade any legacy data (which also does backfill & drops old indexes)
    _upgrade_legacy_data()

    from app.services.jti.quiz_bank_store import get_quiz_bank_store
    store = get_quiz_bank_store()
    
    # Trigger new unique index creation in case it didn't run properly
    store._ensure_indexes()

    for lang, path in QUIZ_BANK_PATHS.items():
        if not path.exists():
            logger.info("[Startup] Quiz bank JSON not found for %s: %s", lang, path)
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        existing_meta = store.get_metadata(lang, bank_id=DEFAULT_BANK_ID)
        existing_questions = store.list_questions(lang, DEFAULT_BANK_ID)

        # 判斷需在 upsert 前完成,避免 JSON 同步覆寫使用者已啟用的自訂 bank。
        has_active_bank = store.get_metadata(lang) is not None

        if not _default_bank_is_outdated(existing_meta, existing_questions, data):
            logger.debug("Quiz bank (%s) up to date, skipping", lang)
            continue

        # Upsert metadata with multi-set fields (內容同步,不含 is_active)。
        store.upsert_metadata(lang, DEFAULT_BANK_ID, _default_bank_seed_payload(data))

        if not has_active_bank:
            store.set_active_bank(lang, DEFAULT_BANK_ID)
            logger.info("[Startup] Activated default quiz bank (%s) on first seed", lang)

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

    # Backfill store_name first
    _backfill_store_name(db)

    col = db["quiz_results"]
    legacy_docs = list(col.find({"set_id": {"$exists": False}}))
    for doc in legacy_docs:
        lang = doc.get("language")
        quiz_id = doc.get("quiz_id")
        store_name = doc.get("store_name", JTI_STORE_NAME)
        existing = col.find_one({"store_name": store_name, "language": lang, "set_id": DEFAULT_SET_ID, "quiz_id": quiz_id})
        if existing:
            col.delete_one({"_id": doc["_id"]})
        else:
            col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"set_id": DEFAULT_SET_ID}},
            )
    if legacy_docs:
        logger.info("[Startup] Processed %d legacy quiz result docs", len(legacy_docs))

    # 原子建立 default set metadata,避免啟動/併發時重複 insert。
    meta_col = db["quiz_results_metadata"]
    for lang in ["zh", "en"]:
        now = datetime.now(timezone.utc)
        meta_col.update_one(
            {"store_name": JTI_STORE_NAME, "language": lang, "set_id": DEFAULT_SET_ID},
            {
                "$setOnInsert": {
                    "store_name": JTI_STORE_NAME,
                    "language": lang,
                    "set_id": DEFAULT_SET_ID,
                    "name": _default_quiz_results_set_payload(lang)["name"],
                    "is_active": True,
                    "is_default": True,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )


def migrate_quiz_results() -> None:
    """Seed quiz results from JSON → MongoDB and sync stale default sets."""
    # First, upgrade any legacy data
    _upgrade_legacy_quiz_results()

    from app.services.jti.quiz_results_store import get_quiz_results_store
    store = get_quiz_results_store()
    
    # Trigger new unique index creation
    store._ensure_indexes()

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
