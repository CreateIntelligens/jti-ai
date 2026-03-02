import unittest

from app.services.jti.migrate_quiz_bank import _default_bank_is_outdated


class TestMigrateQuizBank(unittest.TestCase):
    def setUp(self):
        self.seed_data = {
            "title": "Lifestyle Personality Explorer",
            "description": "Answer a few simple questions.",
            "total_questions": 4,
            "dimensions": ["analyst", "diplomat", "guardian", "explorer"],
            "tie_breaker_priority": ["analyst", "diplomat", "guardian", "explorer"],
            "selection_rules": {"total": 4},
            "questions": [
                {
                    "id": "q1",
                    "text": "Question 1",
                    "weight": 1,
                    "options": [{"id": "a", "text": "A", "score": {"analyst": 1}}],
                },
                {
                    "id": "q2",
                    "text": "Question 2",
                    "weight": 1,
                    "options": [{"id": "a", "text": "B", "score": {"guardian": 1}}],
                },
            ],
        }
        self.existing_meta = {
            "title": self.seed_data["title"],
            "description": self.seed_data["description"],
            "total_questions": self.seed_data["total_questions"],
            "dimensions": self.seed_data["dimensions"],
            "tie_breaker_priority": self.seed_data["tie_breaker_priority"],
            "selection_rules": self.seed_data["selection_rules"],
        }

    def test_no_sync_when_default_bank_matches_seed(self):
        self.assertFalse(
            _default_bank_is_outdated(
                self.existing_meta,
                self.seed_data["questions"],
                self.seed_data,
            )
        )

    def test_sync_when_metadata_differs(self):
        stale_meta = dict(self.existing_meta)
        stale_meta["total_questions"] = 120

        self.assertTrue(
            _default_bank_is_outdated(
                stale_meta,
                self.seed_data["questions"],
                self.seed_data,
            )
        )

    def test_sync_when_questions_differ(self):
        stale_questions = [
            {
                "id": "q1",
                "text": "Old question text",
                "weight": 1,
                "options": [{"id": "a", "text": "Old", "score": {"legacy": 1}}],
            }
        ]

        self.assertTrue(
            _default_bank_is_outdated(
                self.existing_meta,
                stale_questions,
                self.seed_data,
            )
        )


if __name__ == "__main__":
    unittest.main()
