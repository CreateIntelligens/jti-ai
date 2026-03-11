import unittest

from app.services.jti.migrate_quiz_bank import _default_quiz_results_are_outdated


class TestMigrateQuizResults(unittest.TestCase):
    def setUp(self):
        self.seed_data = {
            "analyst": {
                "title": "Maximize Every Moment",
                "color_name": "Analyst",
                "recommended_colors": ["Silver Gray", "Black"],
                "description": "English description.",
            }
        }
        self.zh_meta = {
            "name": "預設測驗結果",
            "is_active": True,
            "is_default": True,
        }
        self.en_meta = {
            "name": "Default Quiz Results",
            "is_active": True,
            "is_default": True,
        }

    def test_no_sync_when_en_results_match_seed(self):
        self.assertFalse(
            _default_quiz_results_are_outdated(
                self.en_meta,
                self.seed_data,
                self.seed_data,
                "en",
            )
        )

    def test_sync_when_metadata_differs(self):
        stale_meta = dict(self.zh_meta)
        stale_meta["name"] = "Old Name"

        self.assertTrue(
            _default_quiz_results_are_outdated(
                stale_meta,
                self.seed_data,
                self.seed_data,
                "zh",
            )
        )

    def test_sync_when_results_differ(self):
        stale_results = {
            "analyst": {
                "title": "Old Title",
                "color_name": "Old Name",
                "recommended_colors": ["Old"],
                "description": "Old description.",
            }
        }

        self.assertTrue(
            _default_quiz_results_are_outdated(
                self.en_meta,
                stale_results,
                self.seed_data,
                "en",
            )
        )


if __name__ == "__main__":
    unittest.main()
