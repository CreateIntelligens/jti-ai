"""
MongoDB-backed quiz bank storage with multi-set support.

Stores quiz questions and metadata in collections:
- quiz_bank_questions: individual question documents (keyed by language + bank_id + id)
- quiz_bank_metadata: quiz configuration per bank (keyed by language + bank_id)

Max 3 banks per language.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ReturnDocument

from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)

MAX_BANKS = 3
DEFAULT_BANK_ID = "default"


class QuizBankStore:
    """MongoDB-backed quiz bank storage with multi-set support."""

    QUESTIONS_COLLECTION = "quiz_bank_questions"
    METADATA_COLLECTION = "quiz_bank_metadata"

    def __init__(self):
        self.db = get_mongo_db()
        self.questions = self.db[self.QUESTIONS_COLLECTION]
        self.metadata = self.db[self.METADATA_COLLECTION]

    # ===================== Bank Management =====================

    def list_banks(self, language: str) -> list[dict]:
        """List all banks for a language."""
        cursor = self.metadata.find(
            {"language": language},
            {"_id": 0},
        ).sort("created_at", 1)
        banks = list(cursor)
        # Add question count per bank
        for bank in banks:
            bank["question_count"] = self.questions.count_documents(
                {"language": language, "bank_id": bank.get("bank_id")}
            )
        return banks

    def create_bank(self, language: str, name: str) -> dict:
        """Create new empty bank. Raises if at max."""
        count = self.metadata.count_documents({"language": language})
        if count >= MAX_BANKS:
            raise ValueError(f"Maximum {MAX_BANKS} banks per language")

        now = datetime.now(timezone.utc)
        bank_id = str(uuid.uuid4())[:8]
        doc = {
            "language": language,
            "bank_id": bank_id,
            "name": name,
            "quiz_id": "color_taste",
            "title": name,
            "description": "",
            "total_questions": 5,
            "dimensions": ["metal", "cool", "warm", "dark", "colorful"],
            "tie_breaker_priority": ["metal", "cool", "warm", "dark", "colorful"],
            "selection_rules": {
                "total": 5,
                "required": {"personality": 1, "random_from": ["food", "style", "lifestyle", "home", "mood"]},
            },
            "is_active": False,
            "is_default": False,
            "created_at": now,
            "updated_at": now,
        }
        self.metadata.insert_one(doc)
        doc.pop("_id", None)
        doc["question_count"] = 0
        return doc

    def delete_bank(self, language: str, bank_id: str) -> bool:
        """Delete a bank and its questions. Cannot delete default bank."""
        meta = self.metadata.find_one({"language": language, "bank_id": bank_id})
        if not meta:
            return False
        if meta.get("is_default"):
            raise ValueError("Cannot delete the default bank")

        was_active = meta.get("is_active", False)
        self.questions.delete_many({"language": language, "bank_id": bank_id})
        self.metadata.delete_one({"language": language, "bank_id": bank_id})

        # If deleted bank was active, activate the default
        if was_active:
            self.metadata.update_one(
                {"language": language, "bank_id": DEFAULT_BANK_ID},
                {"$set": {"is_active": True}},
            )
        return True

    def set_active_bank(self, language: str, bank_id: str) -> bool:
        """Set a bank as active, deactivate others."""
        meta = self.metadata.find_one({"language": language, "bank_id": bank_id})
        if not meta:
            return False
        self.metadata.update_many(
            {"language": language},
            {"$set": {"is_active": False}},
        )
        self.metadata.update_one(
            {"language": language, "bank_id": bank_id},
            {"$set": {"is_active": True}},
        )
        return True

    # ===================== Metadata CRUD =====================

    def get_metadata(self, language: str, bank_id: str | None = None) -> dict | None:
        """Get quiz bank metadata. If bank_id is None, returns the active bank."""
        if bank_id:
            query = {"language": language, "bank_id": bank_id}
        else:
            query = {"language": language, "is_active": True}
        doc = self.metadata.find_one(query, {"_id": 0})
        return doc

    def upsert_metadata(self, language: str, bank_id: str, data: dict) -> dict:
        """Upsert quiz bank metadata."""
        now = datetime.now(timezone.utc)
        update_data = {
            k: v for k, v in data.items() if k not in ("_id", "language", "bank_id")
        }
        update_data["language"] = language
        update_data["bank_id"] = bank_id
        update_data["updated_at"] = now
        doc = self.metadata.find_one_and_update(
            {"language": language, "bank_id": bank_id},
            {"$set": update_data, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        return doc

    # ===================== Question CRUD =====================

    def list_questions(
        self, language: str, bank_id: str | None = None, category: str | None = None
    ) -> list[dict]:
        """List questions for a bank. If bank_id is None, uses active bank."""
        if not bank_id:
            meta = self.get_metadata(language)
            bank_id = meta["bank_id"] if meta else DEFAULT_BANK_ID

        query: dict[str, Any] = {"language": language, "bank_id": bank_id}
        if category:
            query["category"] = category
        cursor = self.questions.find(
            query, {"_id": 0, "language": 0, "bank_id": 0}
        ).sort("id", 1)
        return list(cursor)

    def get_question(self, language: str, bank_id: str, question_id: str) -> dict | None:
        doc = self.questions.find_one(
            {"language": language, "bank_id": bank_id, "id": question_id},
            {"_id": 0, "language": 0, "bank_id": 0},
        )
        return doc

    def create_question(self, language: str, bank_id: str, question: dict) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            **question,
            "language": language,
            "bank_id": bank_id,
            "created_at": now,
            "updated_at": now,
        }
        self.questions.insert_one(doc)
        doc.pop("_id", None)
        doc.pop("language", None)
        doc.pop("bank_id", None)
        return doc

    def update_question(
        self, language: str, bank_id: str, question_id: str, question: dict
    ) -> dict | None:
        now = datetime.now(timezone.utc)
        update_data = {
            k: v for k, v in question.items() if k not in ("_id", "language", "bank_id")
        }
        update_data["updated_at"] = now

        doc = self.questions.find_one_and_update(
            {"language": language, "bank_id": bank_id, "id": question_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc.pop("language", None)
        doc.pop("bank_id", None)
        return doc

    def delete_question(self, language: str, bank_id: str, question_id: str) -> bool:
        result = self.questions.delete_one(
            {"language": language, "bank_id": bank_id, "id": question_id}
        )
        return result.deleted_count > 0

    def bulk_upsert_questions(self, language: str, bank_id: str, questions: list[dict]) -> int:
        """Bulk upsert questions into a bank."""
        if not questions:
            return 0
        now = datetime.now(timezone.utc)
        count = 0
        for q in questions:
            self.questions.update_one(
                {"language": language, "bank_id": bank_id, "id": q["id"]},
                {
                    "$set": {**q, "language": language, "bank_id": bank_id, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            count += 1
        return count

    def replace_all_questions(self, language: str, bank_id: str, questions: list[dict]) -> int:
        """Replace all questions in a bank (delete then insert)."""
        self.questions.delete_many({"language": language, "bank_id": bank_id})
        return self.bulk_upsert_questions(language, bank_id, questions)

    # ===================== Full Bank Export =====================

    def get_full_bank(self, language: str) -> dict | None:
        """Reassemble active bank's metadata + questions for quiz.py."""
        meta = self.get_metadata(language)
        if not meta:
            return None

        bank_id = meta.get("bank_id", DEFAULT_BANK_ID)
        questions = self.list_questions(language, bank_id)
        clean_questions = []
        for q in questions:
            clean_q = {
                k: v for k, v in q.items()
                if k not in ("created_at", "updated_at")
            }
            clean_questions.append(clean_q)

        return {
            "quiz_id": meta.get("quiz_id", ""),
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "total_questions": meta.get("total_questions", 5),
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
