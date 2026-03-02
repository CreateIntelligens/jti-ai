import random
import unittest

from app.models.session import Session
from app.tools.quiz import generate_random_quiz, load_quiz_bank, complete_selected_questions
from app.tools.color_results import calculate_color_result


class TestColorQuizSession(unittest.TestCase):
    def test_session_defaults_for_color_quiz(self):
        session = Session()
        data = session.model_dump()
        self.assertIn("color_result_id", data)
        self.assertIsNone(data["color_result_id"])
        self.assertEqual(data["color_scores"], {})

    def test_generate_random_quiz_selection_rules(self):
        random.seed(7)
        questions = generate_random_quiz(language="zh")
        self.assertEqual(len(questions), 4)
        categories = [q.get("category") for q in questions]
        self.assertTrue(all(category == "personality" for category in categories))
        rules = load_quiz_bank(language="zh").get("selection_rules", {})
        self.assertEqual(rules.get("total"), 4)
        self.assertEqual(len({q["id"] for q in questions}), 4)

    def test_calculate_color_result_tie_breaker(self):
        result = calculate_color_result({"q1": "a", "q2": "b"}, language="zh")
        self.assertEqual(result["color_id"], "analyst")
        self.assertEqual(result["color_scores"]["analyst"], 1)
        self.assertEqual(result["color_scores"]["diplomat"], 1)

    def test_complete_selected_questions_fills_missing_slots(self):
        random.seed(42)
        selected = generate_random_quiz(language="zh")
        partial = selected[:3]

        completed = complete_selected_questions(partial, language="zh")

        self.assertEqual(len(completed), 4)
        self.assertEqual([q["id"] for q in completed[:3]], [q["id"] for q in partial])
        self.assertEqual(len({q["id"] for q in completed}), 4)
