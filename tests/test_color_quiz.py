import random
import unittest

from app.models.session import Session
from app.tools.quiz import generate_random_quiz, load_quiz_bank, complete_selected_questions
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
        # c1/a → metal:2, c2/b → dark:2; tie_breaker_priority: metal first
        self.assertEqual(result["color_id"], "metal")
        self.assertEqual(result["color_scores"]["metal"], 2)
        self.assertEqual(result["color_scores"]["dark"], 2)

    def test_complete_selected_questions_fills_missing_slots(self):
        random.seed(42)
        selected = generate_random_quiz(language="zh")
        partial = selected[:3]

        completed = complete_selected_questions(partial, language="zh")

        self.assertEqual(len(completed), 5)
        self.assertEqual([q["id"] for q in completed[:3]], [q["id"] for q in partial])
        self.assertEqual(len({q["id"] for q in completed}), 5)
