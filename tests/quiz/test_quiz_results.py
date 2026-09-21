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
        self.assertEqual(len(questions), 3)
        self.assertTrue(all("category" not in question for question in questions))
        rules = load_quiz_bank(language="zh").get("selection_rules", {})
        self.assertEqual(rules.get("total"), 3)
        self.assertEqual(len({q["id"] for q in questions}), 3)

        # 確保抽取的 3 題涵蓋題庫全部答案/維度種類
        covered_dims = {
            dim
            for q in questions
            for opt in q.get("options", [])
            for dim in opt.get("score", {})
        }
        self.assertEqual(covered_dims, {"analyst", "diplomat", "guardian", "explorer"})

    def test_calculate_quiz_result_tie_breaker(self):
        result = calculate_quiz_result({"q1": "a", "q2": "b"}, language="zh")
        self.assertEqual(result["quiz_id"], "analyst")
        self.assertEqual(result["quiz_scores"]["analyst"], 1)
        self.assertEqual(result["quiz_scores"]["diplomat"], 1)

    def test_complete_selected_questions_fills_missing_slots(self):
        random.seed(42)
        selected = generate_random_quiz(language="zh")
        partial = selected[:2]

        completed = complete_selected_questions(partial, language="zh")

        self.assertEqual(len(completed), 3)
        self.assertEqual([q["id"] for q in completed[:2]], [q["id"] for q in partial])
        self.assertEqual(len({q["id"] for q in completed}), 3)

    def test_select_diverse_questions_covers_all_types(self):
        from app.tools.jti.quiz import select_diverse_questions, _extract_question_answer_types

        # 模擬 6 題知識問答，答案各有 a, b, c
        mock_qs = [
            {"id": "q1", "options": [{"id": "a", "score": {"correct": 1}}, {"id": "b", "score": {"correct": 0}}]},
            {"id": "q2", "options": [{"id": "a", "score": {"correct": 1}}, {"id": "b", "score": {"correct": 0}}]},
            {"id": "q3", "options": [{"id": "b", "score": {"correct": 1}}, {"id": "a", "score": {"correct": 0}}]},
            {"id": "q4", "options": [{"id": "b", "score": {"correct": 1}}, {"id": "a", "score": {"correct": 0}}]},
            {"id": "q5", "options": [{"id": "c", "score": {"correct": 1}}, {"id": "a", "score": {"correct": 0}}]},
            {"id": "q6", "options": [{"id": "c", "score": {"correct": 1}}, {"id": "a", "score": {"correct": 0}}]},
        ]
        sampled = select_diverse_questions(mock_qs, 3)
        self.assertEqual(len(sampled), 3)
        covered = set.union(*(_extract_question_answer_types(q) for q in sampled))
        self.assertEqual(covered, {"a", "b", "c"})
