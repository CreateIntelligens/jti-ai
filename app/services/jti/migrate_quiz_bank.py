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
from app.services.db_names import CONTROL_PLANE_DB_NAME
from app.services.quiz.config import JTI_STORE_NAME

logger = logging.getLogger(__name__)

QUIZ_SEED_TABLE = [
    # (managed_app, store_name, language, json_path)
    ("jti", "__jti__",   "zh", "data/jti/quiz_bank_zh.json"),
    ("jti", "__jti__en", "en", "data/jti/quiz_bank_en.json"),
    ("esg", "__esg__",   "zh", "data/esg/quiz_bank_zh.json"),
    ("esg", "__esg__en", "en", "data/esg/quiz_bank_en.json"),
]

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


def _load_bank(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return next(iter(data["quiz_sets"].values()))


# DB/system fields excluded when comparing stored docs against JSON seed content.
_INTERNAL_DOC_FIELDS = ("created_at", "updated_at", "store_name", "language", "bank_id", "set_id", "quiz_id")


def _strip_internal_fields(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k not in _INTERNAL_DOC_FIELDS}


def _default_bank_seed_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Default bank 的「內容」欄位 (JSON 同步用)。

    不含 is_active: active 是執行期狀態,只在首次播種時補上 default。
    之後 JSON 同步只更新內容欄位,避免覆寫使用者已啟用的自訂 bank。
    """
    return {
        "name": data.get("name", "預設題庫"),
        "title": data.get("title", data.get("name", "")),
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
        "name",
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
    clean_existing = [_strip_internal_fields(q) for q in existing_questions]
    clean_expected = [_strip_internal_fields(q) for q in expected_questions]
    return clean_existing != clean_expected


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

    clean_existing = {qid: _strip_internal_fields(doc) for qid, doc in existing_results.items()}
    clean_seed = {qid: _strip_internal_fields(doc) for qid, doc in seed_data.items()}
    return clean_existing != clean_seed


def migrate_esg_legacy_data() -> None:
    """Migrate legacy ESG dynamic store data to new fixed app stores (__esg__ / __esg__en)."""
    from app.services.mongo_client import get_mongo_db

    db_control = get_mongo_db(CONTROL_PLANE_DB_NAME)
    db_jti = get_mongo_db("jti_app")
    db_general = get_mongo_db("general_app")

    if db_control is None or db_jti is None or db_general is None:
        return

    mapping = {
        "store_95028fc06029": "__esg__",    # ESG_ZH
        "store_b66923e91295": "__esg__en",  # ESG_EN
    }

    # 1. system_config.knowledge_stores (store registry)
    # __esg__/__esg__en are fixed managed stores defined in MANAGED_STORES, so
    # they must NOT also exist as dynamic registry docs — a duplicate doc makes
    # the store list show each ESG store twice. Drop the legacy hash registration
    # entirely (its data is migrated to the fixed store below); also clean up any
    # stray registry doc that previously got renamed to the fixed name.
    col_stores = db_control["knowledge_stores"]
    for old_name, new_name in mapping.items():
        removed = col_stores.delete_many({"name": {"$in": [old_name, new_name]}}).deleted_count
        if removed:
            logger.info("[Migration] Removed %d legacy ESG registry doc(s) for %s", removed, new_name)

    # Helper for safe rename to prevent duplicate key errors
    def safe_rename(collection, filter_keys, old_store, new_store):
        cursor = collection.find({**filter_keys, "store_name": old_store})
        for doc in cursor:
            target_filter = {k: doc[k] for k in filter_keys}
            target_filter["store_name"] = new_store
            existing = collection.find_one(target_filter)
            if existing:
                collection.delete_one({"_id": doc["_id"]})
            else:
                collection.update_one({"_id": doc["_id"]}, {"$set": {"store_name": new_store}})

    # 2. system_config.prompts
    col_prompts = db_control["prompts"]
    for old_name, new_name in mapping.items():
        safe_rename(col_prompts, {}, old_name, new_name)

    # 3. jti_app.quiz_bank_metadata / quiz_bank_questions
    col_bank_meta = db_jti["quiz_bank_metadata"]
    col_bank_qs = db_jti["quiz_bank_questions"]
    for old_name, new_name in mapping.items():
        safe_rename(col_bank_meta, {"language": {"$exists": True}, "bank_id": {"$exists": True}}, old_name, new_name)
        safe_rename(col_bank_qs, {"language": {"$exists": True}, "bank_id": {"$exists": True}, "id": {"$exists": True}}, old_name, new_name)

    # 4. jti_app.quiz_results_metadata / quiz_results
    col_res_meta = db_jti["quiz_results_metadata"]
    col_res = db_jti["quiz_results"]
    for old_name, new_name in mapping.items():
        safe_rename(col_res_meta, {"language": {"$exists": True}, "set_id": {"$exists": True}}, old_name, new_name)
        safe_rename(col_res, {"language": {"$exists": True}, "set_id": {"$exists": True}, "quiz_id": {"$exists": True}}, old_name, new_name)

    # 5. general_app.conversations
    col_convs = db_general["conversations"]
    for old_name, new_name in mapping.items():
        col_convs.update_many({"store_name": old_name}, {"$set": {"store_name": new_name}})


def migrate_quiz_bank() -> None:
    """Seed quiz bank from JSON → MongoDB and sync stale default banks."""
    # Run legacy ESG data migration first
    migrate_esg_legacy_data()

    # Upgrade any JTI legacy data
    _upgrade_legacy_data()

    from app.services.jti.quiz_bank_store import get_quiz_bank_store
    store = get_quiz_bank_store()
    store._ensure_indexes()

    import app.deps as deps

    for _app, store_name, lang, json_path in QUIZ_SEED_TABLE:
        path = Path(json_path)
        if not path.exists():
            logger.info("[Startup] Quiz bank JSON not found: %s", path)
            continue

        try:
            bank = _load_bank(path)
        except Exception as exc:
            logger.warning("[Startup] Failed to load quiz bank %s: %s", path, exc)
            continue

        existing_meta = store.get_metadata(lang, bank_id=DEFAULT_BANK_ID, store_name=store_name)
        existing_questions = store.list_questions(lang, DEFAULT_BANK_ID, store_name=store_name)

        has_active_bank = store.get_metadata(lang, store_name=store_name) is not None

        if _default_bank_is_outdated(existing_meta, existing_questions, bank):
            store.upsert_metadata(lang, DEFAULT_BANK_ID, _default_bank_seed_payload(bank), store_name=store_name)

            if not has_active_bank:
                store.set_active_bank(lang, DEFAULT_BANK_ID, store_name=store_name)
                logger.info("[Startup] Activated default quiz bank (%s) on first seed", store_name)

            questions = bank.get("questions", [])
            count = store.replace_all_questions(lang, DEFAULT_BANK_ID, questions, store_name=store_name)
            logger.info("[Startup] Synced quiz bank (%s, %s): %d questions", store_name, lang, count)
        else:
            logger.debug("Quiz bank (%s, %s) up to date, skipping", store_name, lang)

        # Seed prompts (quiz_copy and enable quiz)
        pm = deps.prompt_manager
        if pm:
            try:
                sp = pm.get_store_prompts(store_name)
                sp.quiz_enabled = True
                if "測驗" not in sp.quiz_start_keywords:
                    sp.quiz_start_keywords = list(sp.quiz_start_keywords) + ["測驗", "quiz", "問答"]

                quiz_copy = bank.get("quiz_copy")
                if quiz_copy:
                    sp.quiz_copy = quiz_copy

                pm.save_store_prompts(sp)
            except Exception as exc:
                logger.warning("[Startup] Failed to seed prompts for %s: %s", store_name, exc)


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
    # First, upgrade any JTI legacy results
    _upgrade_legacy_quiz_results()

    from app.services.jti.quiz_results_store import get_quiz_results_store
    store = get_quiz_results_store()
    store._ensure_indexes()

    for _app, store_name, lang, json_path in QUIZ_SEED_TABLE:
        path = Path(json_path)
        if not path.exists():
            logger.info("[Startup] Quiz results JSON not found: %s", path)
            continue

        try:
            bank = _load_bank(path)
        except Exception as exc:
            logger.warning("[Startup] Failed to load quiz bank for results %s: %s", path, exc)
            continue

        results_data = bank.get("results")
        if not results_data:
            logger.debug("No results in quiz bank (%s, %s), skipping results seed", store_name, lang)
            continue

        existing_meta = store.get_set_metadata(lang, DEFAULT_SET_ID, store_name=store_name)
        existing_results = store.get_all_results(lang, set_id=DEFAULT_SET_ID, store_name=store_name)

        if not _default_quiz_results_are_outdated(existing_meta, existing_results, results_data, lang):
            logger.debug("Quiz results (%s, %s) up to date, skipping", store_name, lang)
            continue

        store.upsert_set_metadata(lang, DEFAULT_SET_ID, _default_quiz_results_set_payload(lang), store_name=store_name)
        count = store.replace_all_results(lang, results_data, set_id=DEFAULT_SET_ID, store_name=store_name)
        logger.info("[Startup] Synced quiz results (%s, %s): %d entries", store_name, lang, count)
