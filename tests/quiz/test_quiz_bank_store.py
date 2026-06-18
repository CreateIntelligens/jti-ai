import unittest
from unittest.mock import MagicMock

from app.services.jti.quiz_bank_store import QuizBankStore
from app.services.quiz.config import JTI_STORE_NAME


class TestQuizBankStore(unittest.TestCase):
    def setUp(self):
        self.store = QuizBankStore.__new__(QuizBankStore)
        self.store.metadata = MagicMock()
        self.store.questions = MagicMock()

    def test_create_bank_clones_default_bank_metadata_and_questions(self):
        self.store.metadata.count_documents.return_value = 1
        self.store.metadata.find_one.return_value = {
            "language": "zh",
            "bank_id": "default",
            "title": "Default Title",
            "description": "Default Description",
            "total_questions": 4,
            "dimensions": ["analyst", "diplomat", "guardian", "explorer"],
            "tie_breaker_priority": ["analyst", "diplomat", "guardian", "explorer"],
            "selection_rules": {"total": 4},
            "is_active": True,
            "is_default": True,
        }
        self.store.questions.find.return_value = [
            {
                "language": "zh",
                "bank_id": "default",
                "id": "q1",
                "text": "Question 1",
                "weight": 1,
                "options": [{"id": "a", "text": "A", "score": {"analyst": 1}}],
            },
            {
                "language": "zh",
                "bank_id": "default",
                "id": "q2",
                "text": "Question 2",
                "weight": 1,
                "options": [{"id": "a", "text": "B", "score": {"guardian": 1}}],
            },
        ]

        bank = self.store.create_bank("zh", "My Copy")

        self.assertEqual(bank["name"], "My Copy")
        self.assertEqual(bank["title"], "My Copy")
        self.assertEqual(bank["description"], "Default Description")
        self.assertEqual(bank["total_questions"], 4)
        self.assertEqual(bank["question_count"], 2)
        self.store.questions.insert_many.assert_called_once()
        inserted_docs = self.store.questions.insert_many.call_args.args[0]
        self.assertEqual(len(inserted_docs), 2)
        self.assertTrue(all(doc["bank_id"] == bank["bank_id"] for doc in inserted_docs))
        self.assertTrue(all(doc["language"] == "zh" for doc in inserted_docs))

    def test_get_metadata_repairs_multiple_active_banks(self):
        active_banks = [
            {"bank_id": "copy", "is_active": True, "is_default": False, "created_at": 2},
            {"bank_id": "default", "is_active": True, "is_default": True, "created_at": 1},
        ]
        self.store.metadata.find.return_value.sort.return_value = active_banks

        result = self.store.get_metadata("zh")

        self.assertEqual(result["bank_id"], "copy")
        self.store.metadata.update_many.assert_called_once_with(
            {
                "store_name": JTI_STORE_NAME,
                "language": "zh",
                "is_active": True,
                "bank_id": {"$ne": "copy"},
            },
            {"$set": {"is_active": False}},
        )

    def test_list_banks_repairs_multiple_active_banks_before_listing(self):
        active_cursor = MagicMock()
        active_cursor.sort.return_value = [
            {"bank_id": "copy", "is_active": True, "is_default": False, "created_at": 2},
            {"bank_id": "default", "is_active": True, "is_default": True, "created_at": 1},
        ]
        list_cursor = MagicMock()
        list_cursor.sort.return_value = [
            {"bank_id": "default", "is_active": False},
            {"bank_id": "copy", "is_active": True},
        ]
        self.store.metadata.find.side_effect = [active_cursor, list_cursor]
        self.store.questions.count_documents.return_value = 4

        banks = self.store.list_banks("zh")

        self.assertEqual([bank["bank_id"] for bank in banks if bank["is_active"]], ["copy"])
        self.store.metadata.update_many.assert_called_once()


if __name__ == "__main__":
    unittest.main()
