"""
Quiz 工具：產生題目

職責：
1. 從題庫隨機抽題（每個維度隨機選一題）
2. 回傳結構化資料
3. LLM 不得自行生成題目
"""

import json
import random
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


def generate_random_quiz(quiz_id: str = "mbti_quick") -> List[Dict]:
    """
    產生隨機測驗題目

    策略：
    - 4 個 MBTI 維度 (E_I, S_N, T_F, J_P) 各隨機抽 1 題
    - 最後從剩餘題目中隨機抽 1 題
    - 總共 5 題

    Args:
        quiz_id: 題庫 ID

    Returns:
        List of 5 selected questions
    """
    try:
        quiz_bank = load_quiz_bank()
        quiz_set = quiz_bank["quiz_sets"].get(quiz_id)

        if not quiz_set:
            raise ValueError(f"Quiz set '{quiz_id}' not found")

        all_questions = quiz_set["questions"]

        # 按維度分組
        dimensions = {}
        for q in all_questions:
            dim = q.get("dimension", "UNKNOWN")
            if dim not in dimensions:
                dimensions[dim] = []
            dimensions[dim].append(q)

        selected = []
        used_questions = set()

        # 每個主要維度隨機抽 1 題
        for dim in ["E_I", "S_N", "T_F", "J_P"]:
            if dim in dimensions and dimensions[dim]:
                question = random.choice(dimensions[dim])
                selected.append(question)
                used_questions.add(question["id"])

        # 從剩餘題目隨機抽 1 題
        remaining = [q for q in all_questions if q["id"] not in used_questions]
        if remaining:
            selected.append(random.choice(remaining))

        logger.info(f"Generated random quiz: {quiz_id}, selected {len(selected)} questions: {[q['id'] for q in selected]}")
        return selected

    except Exception as e:
        logger.error(f"Failed to generate random quiz: {e}")
        raise


def generate_quiz(quiz_id: str = "mbti_quick") -> Dict:
    """
    產生測驗題目（向後相容的 wrapper）

    Returns:
        {
            "quiz_id": str,
            "name": str,
            "description": str,
            "total_questions": int,
            "questions": list (5 randomly selected questions)
        }
    """
    try:
        quiz_bank = load_quiz_bank()
        quiz_set = quiz_bank["quiz_sets"].get(quiz_id)

        if not quiz_set:
            raise ValueError(f"Quiz set '{quiz_id}' not found")

        # 隨機抽 5 題
        questions = generate_random_quiz(quiz_id)

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


def get_question_from_selected(selected_questions: List[Dict], question_index: int) -> Optional[Dict]:
    """
    從已選中的題目列表中取得單一題目

    Args:
        selected_questions: 已隨機選中的題目列表
        question_index: 題目索引（0-based）

    Returns:
        題目資料或 None
    """
    try:
        if question_index < 0 or question_index >= len(selected_questions):
            return None
        return selected_questions[question_index]
    except Exception as e:
        logger.error(f"Failed to get question from selected: {e}")
        return None


def get_question(quiz_id: str, question_index: int) -> Optional[Dict]:
    """
    取得單一題目（向後相容，但不建議使用）

    Args:
        quiz_id: 題庫 ID
        question_index: 題目索引（0-based）

    Returns:
        題目資料或 None
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


def get_total_questions(quiz_id: str = "mbti_quick") -> int:
    """取得題庫總題數（隨機測驗固定為 5 題）"""
    return 5
