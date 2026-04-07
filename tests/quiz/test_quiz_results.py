import random
import unittest

from app.models.session import Session
from app.tools.jti.quiz import generate_random_quiz, load_quiz_bank, complete_selected_questions
from app.tools.jti.quiz_results import calculate_quiz_result


class TestQuizResults(unittest.TestCase):
    def test_session_defaults_for_quiz_results(self):
        session = Session()
        data = session.model_dump()
        self.assertIn("quiz_result_id", data)
        self.assertIsNone(data["quiz_result_id"])
        self.assertEqual(data["quiz_scores"], {})

    def test_generate_random_quiz_selection_rules(self):
        random.seed(7)
        questions = generate_random_quiz(language="zh")
        self.assertEqual(len(questions), 4)
        self.assertTrue(all("category" not in question for question in questions))
        rules = load_quiz_bank(language="zh").get("selection_rules", {})
        self.assertEqual(rules.get("total"), 4)
        self.assertEqual(len({q["id"] for q in questions}), 4)

    def test_calculate_quiz_result_tie_breaker(self):
        result = calculate_quiz_result({"q1": "a", "q2": "b"}, language="zh")
        self.assertEqual(result["quiz_id"], "analyst")
        self.assertEqual(result["quiz_scores"]["analyst"], 1)
        self.assertEqual(result["quiz_scores"]["diplomat"], 1)

    def test_complete_selected_questions_fills_missing_slots(self):
        random.seed(42)
        selected = generate_random_quiz(language="zh")
        partial = selected[:3]

        completed = complete_selected_questions(partial, language="zh")

        self.assertEqual(len(completed), 4)
        self.assertEqual([q["id"] for q in completed[:3]], [q["id"] for q in partial])
        self.assertEqual(len({q["id"] for q in completed}), 4)
