"""
MongoDB-backed quiz bank storage with multi-set support.

Stores quiz questions and metadata in collections:
- quiz_bank_questions: individual question documents (keyed by store_name + language + bank_id + id)
- quiz_bank_metadata: quiz configuration per bank (keyed by store_name + language + bank_id)

Max 3 banks per language.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

from app.services.mongo_client import get_mongo_db
from app.services.quiz.config import JTI_STORE_NAME

logger = logging.getLogger(__name__)

MAX_BANKS = 3
DEFAULT_BANK_ID = "default"


class QuizBankStore:
    """MongoDB-backed quiz bank storage with multi-set support."""

    QUESTIONS_COLLECTION = "quiz_bank_questions"
    METADATA_COLLECTION = "quiz_bank_metadata"

    def __init__(self):
        self.db = get_mongo_db("jti_app")
        self.questions = self.db[self.QUESTIONS_COLLECTION]
        self.metadata = self.db[self.METADATA_COLLECTION]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """確保 metadata / questions 的 unique index 含 store_name。

        Multi-store 改造前的舊 unique index 只用 (language, bank_id[, id]),
        缺 store_name → 第二個 store 用相同 bank_id/題號就會跨 store 撞鍵。
        這裡先 drop 殘留的舊 unique index,再建含 store_name 的正確版本。
        """
        # metadata: 移除舊的 (language, bank_id) unique,改 (store_name, language, bank_id)。
        self._drop_legacy_index(self.metadata, "language_1_bank_id_1")
        try:
            self.metadata.create_index(
                [("store_name", 1), ("language", 1), ("bank_id", 1)],
                unique=True,
                name="store_name_1_language_1_bank_id_1",
            )
        except Exception as exc:  # noqa: BLE001 — 啟動期僅記錄,不阻斷
            logger.warning(
                "[QuizBank] 建立 (store_name, language, bank_id) unique index 失敗: %s", exc
            )

        # questions: 移除舊的 (language, bank_id, id) unique,改含 store_name。
        self._drop_legacy_index(self.questions, "language_1_bank_id_1_id_1")
        try:
            self.questions.create_index(
                [("store_name", 1), ("language", 1), ("bank_id", 1), ("id", 1)],
                unique=True,
                name="store_name_1_language_1_bank_id_1_id_1",
            )
        except Exception as exc:  # noqa: BLE001 — 啟動期僅記錄,不阻斷
            logger.warning(
                "[QuizBank] 建立 questions unique index 失敗: %s", exc
            )

    @staticmethod
    def _drop_legacy_index(collection, index_name: str) -> None:
        """Drop a legacy index if it exists (idempotent, safe on fresh DBs)."""
        try:
            if index_name in collection.index_information():
                collection.drop_index(index_name)
                logger.info("[QuizBank] 已移除殘留舊 index: %s", index_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[QuizBank] 移除舊 index %s 失敗: %s", index_name, exc)

    # ===================== Bank Management =====================

    def _active_bank_sort(self):
        return [("is_default", 1), ("created_at", -1)]

    def _active_bank_query(self, language: str, store_name: str) -> dict[str, Any]:
        return {"store_name": store_name, "language": language, "is_active": True}

    def _repair_multiple_active_banks(self, language: str, store_name: str) -> dict | None:
        active_banks = list(
            self.metadata.find(
                self._active_bank_query(language, store_name),
                {"_id": 0},
            ).sort(self._active_bank_sort())
        )
        if not active_banks:
            return None

        selected = active_banks[0]
        selected_bank_id = selected.get("bank_id")
        if len(active_banks) > 1 and selected_bank_id:
            logger.warning(
                "[QuizBank] %s %s 有 %d 筆 is_active 題庫(預期 1 筆);"
                "暫以 '%s' 為準並自動收斂 active 狀態。",
                store_name,
                language,
                len(active_banks),
                selected_bank_id,
            )
            self.metadata.update_many(
                {
                    **self._active_bank_query(language, store_name),
                    "bank_id": {"$ne": selected_bank_id},
                },
                {"$set": {"is_active": False}},
            )
        return selected

    def list_banks(self, language: str, store_name: str = JTI_STORE_NAME) -> list[dict]:
        """List all banks for a language."""
        self._repair_multiple_active_banks(language, store_name)
        cursor = self.metadata.find(
            {"store_name": store_name, "language": language},
            {"_id": 0},
        ).sort("created_at", 1)
        banks = list(cursor)
        # Add question count per bank
        for bank in banks:
            bank["question_count"] = self.questions.count_documents(
                {"store_name": store_name, "language": language, "bank_id": bank.get("bank_id")}
            )
        return banks

    def create_bank(self, language: str, name: str, store_name: str = JTI_STORE_NAME, clone_default: bool = True) -> dict:
        """Create a new bank by cloning the default bank when available."""
        count = self.metadata.count_documents({"store_name": store_name, "language": language})
        if count >= MAX_BANKS:
            raise ValueError(f"Maximum {MAX_BANKS} banks per language")

        now = datetime.now(timezone.utc)
        bank_id = str(uuid.uuid4())[:8]

        default_meta = {}
        if clone_default:
            default_meta = self.get_metadata(language, DEFAULT_BANK_ID, store_name=store_name) or {}

        doc = {
            "store_name": store_name,
            "language": language,
            "bank_id": bank_id,
            "name": name,
            "title": name,
            "description": default_meta.get("description", ""),
            "total_questions": default_meta.get("total_questions", 4),
            "dimensions": default_meta.get("dimensions", ["analyst", "diplomat", "guardian", "explorer"]),
            "tie_breaker_priority": default_meta.get(
                "tie_breaker_priority",
                ["analyst", "diplomat", "guardian", "explorer"],
            ),
            "selection_rules": default_meta.get("selection_rules", {"total": 4}),
            "is_active": not clone_default,
            "is_default": not clone_default,
            "created_at": now,
            "updated_at": now,
        }
        self.metadata.insert_one(doc)

        default_questions = []
        if clone_default:
            default_questions = list(
                self.questions.find({"store_name": store_name, "language": language, "bank_id": DEFAULT_BANK_ID})
            )
            for question in default_questions:
                question.pop("_id", None)
                question["store_name"] = store_name
                question["language"] = language
                question["bank_id"] = bank_id
                question["created_at"] = now
                question["updated_at"] = now
            if default_questions:
                self.questions.insert_many(default_questions)

        doc.pop("_id", None)
        doc["question_count"] = len(default_questions)
        return doc

    def delete_bank(self, language: str, bank_id: str, store_name: str = JTI_STORE_NAME) -> bool:
        """Delete a bank and its questions. Cannot delete default bank."""
        meta = self.metadata.find_one({"store_name": store_name, "language": language, "bank_id": bank_id})
        if not meta:
            return False
        if meta.get("is_default"):
            raise ValueError("Cannot delete the default bank")

        was_active = meta.get("is_active", False)
        self.questions.delete_many({"store_name": store_name, "language": language, "bank_id": bank_id})
        self.metadata.delete_one({"store_name": store_name, "language": language, "bank_id": bank_id})

        # If deleted bank was active, activate the default
        if was_active:
            self.metadata.update_one(
                {"store_name": store_name, "language": language, "bank_id": DEFAULT_BANK_ID},
                {"$set": {"is_active": True}},
            )
        return True

    def set_active_bank(self, language: str, bank_id: str, store_name: str = JTI_STORE_NAME) -> bool:
        """Set a bank as active, deactivate others."""
        meta = self.metadata.find_one({"store_name": store_name, "language": language, "bank_id": bank_id})
        if not meta:
            return False
        self.metadata.update_many(
            {"store_name": store_name, "language": language},
            {"$set": {"is_active": False}},
        )
        self.metadata.update_one(
            {"store_name": store_name, "language": language, "bank_id": bank_id},
            {"$set": {"is_active": True}},
        )
        return True

    # ===================== Metadata CRUD =====================

    def get_metadata(self, language: str, bank_id: str | None = None, store_name: str = JTI_STORE_NAME) -> dict | None:
        """Get quiz bank metadata. If bank_id is None, returns the active bank."""
        if bank_id:
            doc = self.metadata.find_one(
                {"store_name": store_name, "language": language, "bank_id": bank_id}, {"_id": 0}
            )
            return doc

        return self._repair_multiple_active_banks(language, store_name)

    def upsert_metadata(self, language: str, bank_id: str, data: dict, store_name: str = JTI_STORE_NAME) -> dict:
        """Upsert quiz bank metadata."""
        now = datetime.now(timezone.utc)
        update_data = {
            k: v for k, v in data.items() if k not in ("_id", "store_name", "language", "bank_id")
        }
        update_data["store_name"] = store_name
        update_data["language"] = language
        update_data["bank_id"] = bank_id
        update_data["updated_at"] = now
        doc = self.metadata.find_one_and_update(
            {"store_name": store_name, "language": language, "bank_id": bank_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        return doc

    # ===================== Question CRUD =====================

    def list_questions(self, language: str, bank_id: str | None = None, store_name: str = JTI_STORE_NAME) -> list[dict]:
        """List questions for a bank. If bank_id is None, uses active bank."""
        if not bank_id:
            meta = self.get_metadata(language, store_name=store_name)
            bank_id = meta["bank_id"] if meta else DEFAULT_BANK_ID

        query: dict[str, Any] = {"store_name": store_name, "language": language, "bank_id": bank_id}
        cursor = self.questions.find(
            query, {"_id": 0, "store_name": 0, "language": 0, "bank_id": 0}
        ).sort("id", 1)
        return list(cursor)

    def get_question(self, language: str, bank_id: str, question_id: str, store_name: str = JTI_STORE_NAME) -> dict | None:
        doc = self.questions.find_one(
            {"store_name": store_name, "language": language, "bank_id": bank_id, "id": question_id},
            {"_id": 0, "store_name": 0, "language": 0, "bank_id": 0},
        )
        return doc

    def create_question(self, language: str, bank_id: str, question: dict, store_name: str = JTI_STORE_NAME) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            **question,
            "store_name": store_name,
            "language": language,
            "bank_id": bank_id,
            "created_at": now,
            "updated_at": now,
        }
        self.questions.insert_one(doc)
        doc.pop("_id", None)
        doc.pop("store_name", None)
        doc.pop("language", None)
        doc.pop("bank_id", None)
        return doc

    def update_question(
        self, language: str, bank_id: str, question_id: str, question: dict, store_name: str = JTI_STORE_NAME
    ) -> dict | None:
        now = datetime.now(timezone.utc)
        update_data = {
            k: v for k, v in question.items() if k not in ("_id", "store_name", "language", "bank_id")
        }
        update_data["updated_at"] = now

        doc = self.questions.find_one_and_update(
            {"store_name": store_name, "language": language, "bank_id": bank_id, "id": question_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc.pop("store_name", None)
        doc.pop("language", None)
        doc.pop("bank_id", None)
        return doc

    def delete_question(self, language: str, bank_id: str, question_id: str, store_name: str = JTI_STORE_NAME) -> bool:
        result = self.questions.delete_one(
            {"store_name": store_name, "language": language, "bank_id": bank_id, "id": question_id}
        )
        return result.deleted_count > 0

    def bulk_upsert_questions(self, language: str, bank_id: str, questions: list[dict], store_name: str = JTI_STORE_NAME) -> int:
        """Bulk upsert questions into a bank."""
        if not questions:
            return 0
        now = datetime.now(timezone.utc)
        count = 0
        for q in questions:
            self.questions.update_one(
                {"store_name": store_name, "language": language, "bank_id": bank_id, "id": q["id"]},
                {
                    "$set": {**q, "store_name": store_name, "language": language, "bank_id": bank_id, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            count += 1
        return count

    def replace_all_questions(self, language: str, bank_id: str, questions: list[dict], store_name: str = JTI_STORE_NAME) -> int:
        """Replace all questions in a bank (delete then insert)."""
        self.questions.delete_many({"store_name": store_name, "language": language, "bank_id": bank_id})
        return self.bulk_upsert_questions(language, bank_id, questions, store_name=store_name)

    # ===================== Full Bank Export =====================

    def get_full_bank(self, language: str, store_name: str = JTI_STORE_NAME) -> dict | None:
        """Reassemble active bank's metadata + questions for quiz.py."""
        meta = self.get_metadata(language, store_name=store_name)
        if not meta:
            return None

        bank_id = meta.get("bank_id", DEFAULT_BANK_ID)
        questions = self.list_questions(language, bank_id, store_name=store_name)
        clean_questions = []
        for q in questions:
            clean_q = {
                k: v for k, v in q.items()
                if k not in ("created_at", "updated_at")
            }
            clean_questions.append(clean_q)

        return {
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "total_questions": meta.get("total_questions", 4),
            "questions": clean_questions,
            "dimensions": meta.get("dimensions", []),
            "tie_breaker_priority": meta.get("tie_breaker_priority", []),
            "selection_rules": meta.get("selection_rules", {}),
        }


# --- Singleton ---

_quiz_bank_store: Optional[QuizBankStore] = None


def get_quiz_bank_store() -> QuizBankStore:
    """Return singleton quiz bank store."""
    global _quiz_bank_store
    if _quiz_bank_store is None:
        _quiz_bank_store = QuizBankStore()
    return _quiz_bank_store
