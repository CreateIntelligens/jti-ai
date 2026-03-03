import unittest
from unittest.mock import MagicMock

from app.services.quiz_bank_store import QuizBankStore


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


if __name__ == "__main__":
    unittest.main()
