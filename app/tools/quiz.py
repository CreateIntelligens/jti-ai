"""
Quiz 工具：產生題目

職責：
1. 從題庫隨機/順序抽題
2. 回傳結構化資料
3. LLM 不得自行生成題目
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# 載入題庫
QUIZ_BANK_PATH = Path("data/quiz_bank.json")
quiz_data = None


def load_quiz_bank():
    """載入題庫"""
    global quiz_data
    if quiz_data is None:
        with open(QUIZ_BANK_PATH, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)
    return quiz_data


def generate_quiz(quiz_id: str = "mbti_basic") -> Dict:
    """
    產生測驗題目

    Args:
        quiz_id: 題庫 ID

    Returns:
        {
            "quiz_id": str,
            "name": str,
            "description": str,
            "total_questions": int,
            "questions": list
        }
    """
    try:
        quiz_bank = load_quiz_bank()
        quiz_set = quiz_bank["quiz_sets"].get(quiz_id)

        if not quiz_set:
            raise ValueError(f"Quiz set '{quiz_id}' not found")

        # 回傳完整題目（不隨機，依照順序）
        questions = quiz_set["questions"]

        result = {
            "quiz_id": quiz_id,
            "name": quiz_set["name"],
            "description": quiz_set["description"],
            "total_questions": len(questions),
            "questions": questions,
        }

        logger.info(f"Generated quiz: {quiz_id}, {len(questions)} questions")
        return result

    except Exception as e:
        logger.error(f"Failed to generate quiz: {e}")
        raise


def get_question(quiz_id: str, question_index: int) -> Optional[Dict]:
    """
    取得單一題目

    Args:
        quiz_id: 題庫 ID
        question_index: 題目索引（0-based）

    Returns:
        {
            "id": str,
            "dimension": str,
            "text": str,
            "options": list
        }
    """
    try:
        quiz_bank = load_quiz_bank()
        quiz_set = quiz_bank["quiz_sets"].get(quiz_id)

        if not quiz_set:
            return None

        questions = quiz_set["questions"]
        if question_index < 0 or question_index >= len(questions):
            return None

        return questions[question_index]

    except Exception as e:
        logger.error(f"Failed to get question: {e}")
        return None


def get_total_questions(quiz_id: str) -> int:
    """取得題庫總題數"""
    try:
        quiz_bank = load_quiz_bank()
        quiz_set = quiz_bank["quiz_sets"].get(quiz_id)
        if not quiz_set:
            return 0
        return len(quiz_set["questions"])
    except Exception as e:
        logger.error(f"Failed to get total questions: {e}")
        return 0
