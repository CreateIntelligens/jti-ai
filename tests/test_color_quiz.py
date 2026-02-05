import random
import unittest

from app.models.session import Session
from app.tools.quiz import generate_random_quiz, load_quiz_bank
from app.tools.color_results import calculate_color_result


class TestColorQuizSession(unittest.TestCase):
    def test_session_defaults_for_color_quiz(self):
        session = Session()
        data = session.model_dump()
        self.assertEqual(data["quiz_id"], "color_taste")
        self.assertIn("color_result_id", data)
        self.assertIsNone(data["color_result_id"])
        self.assertEqual(data["color_scores"], {})

    def test_generate_random_quiz_selection_rules(self):
        random.seed(7)
        questions = generate_random_quiz(language="zh")
        self.assertEqual(len(questions), 5)
        categories = [q.get("category") for q in questions]
        self.assertEqual(categories.count("personality"), 1)
        rules = load_quiz_bank().get("selection_rules", {})
        allowed = set(rules.get("required", {}).get("random_from", []))
        for category in categories:
            if category != "personality":
                self.assertIn(category, allowed)
        self.assertEqual(len({q["id"] for q in questions}), 5)

    def test_calculate_color_result_tie_breaker(self):
        result = calculate_color_result({"c1": "a", "c2": "b"})
        self.assertEqual(result["color_id"], "metal")
        self.assertEqual(result["color_scores"]["metal"], 2)
        self.assertEqual(result["color_scores"]["cool"], 2)
