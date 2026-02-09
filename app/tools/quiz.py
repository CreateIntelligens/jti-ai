"""
Quiz 工具：產生色彩測驗題目

職責：
1. 根據 selection_rules 隨機抽題
2. 回傳結構化資料
3. LLM 不得自行生成題目
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# 載入題庫（色彩題庫，支援中英文）
QUIZ_BANK_PATHS = {
    "zh": Path("data/quiz_bank_color_zh.json"),
    "en": Path("data/quiz_bank_color_en.json"),
}
quiz_data_cache = {}


def load_quiz_bank(language: str = "zh"):
    """載入題庫"""
    global quiz_data_cache
    if language not in quiz_data_cache:
        path = QUIZ_BANK_PATHS.get(language, QUIZ_BANK_PATHS["zh"])
        with open(path, "r", encoding="utf-8") as f:
            quiz_data_cache[language] = json.load(f)
    return quiz_data_cache[language]


def generate_random_quiz(quiz_id: str = "color_taste", language: str = "zh") -> List[Dict]:
    """
    產生隨機測驗題目

    策略：
    - 依 selection_rules 的 required 規則抽題
    - 總題數由 selection_rules.total 決定（預設 5 題）

    Args:
        quiz_id: 題庫 ID

    Returns:
        List of 5 selected questions
    """
    try:
        quiz_bank = load_quiz_bank(language)
        all_questions = quiz_bank.get("questions", [])
        selection_rules = quiz_bank.get("selection_rules", {})
        required = selection_rules.get("required", {})
        total_questions = selection_rules.get("total", 5)

        # 按分類分組
        categories: Dict[str, List[Dict]] = {}
        for q in all_questions:
            category = q.get("category", "unknown")
            categories.setdefault(category, []).append(q)

        selected: List[Dict] = []
        used_ids = set()

        # 1) 必選類別（目前：personality 1 題）
        personality_count = required.get("personality", 0)
        if personality_count > 0:
            pool = categories.get("personality", [])
            if pool:
                picked = random.sample(pool, k=min(personality_count, len(pool)))
                selected.extend(picked)
                used_ids.update(q["id"] for q in picked)

        # 2) 從指定分類清單中抽題（不重複）
        remaining = total_questions - len(selected)
        random_from = required.get("random_from", [])
        available_categories = [c for c in random_from if c in categories]

        if remaining > 0 and available_categories:
            chosen_categories = random.sample(
                available_categories,
                k=min(remaining, len(available_categories))
            )
            for category in chosen_categories:
                pool = [q for q in categories.get(category, []) if q["id"] not in used_ids]
                if pool:
                    question = random.choice(pool)
                    selected.append(question)
                    used_ids.add(question["id"])

        # 3) 若仍不足，從剩餘題目補足
        if len(selected) < total_questions:
            remaining_pool = [q for q in all_questions if q["id"] not in used_ids]
            if remaining_pool:
                fill = random.sample(
                    remaining_pool,
                    k=min(total_questions - len(selected), len(remaining_pool))
                )
                selected.extend(fill)
                used_ids.update(q["id"] for q in fill)

        logger.info(
            "Generated random quiz: %s (%s), selected %s questions: %s",
            quiz_id,
            language,
            len(selected),
            [q.get("id") for q in selected],
        )
        return selected

    except Exception as e:
        logger.error(f"Failed to generate random quiz: {e}")
        raise


def generate_quiz(quiz_id: str = "color_taste", language: str = "zh") -> Dict:
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
        quiz_bank = load_quiz_bank(language)

        # 隨機抽題
        questions = generate_random_quiz(quiz_id, language)

        result = {
            "quiz_id": quiz_bank.get("quiz_id", quiz_id),
            "name": quiz_bank.get("title", quiz_id),
            "description": quiz_bank.get("description", ""),
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
        questions = quiz_bank.get("questions", [])
        if question_index < 0 or question_index >= len(questions):
            return None

        return questions[question_index]

    except Exception as e:
        logger.error(f"Failed to get question: {e}")
        return None


def get_total_questions(quiz_id: str = "color_taste") -> int:
    """取得題庫總題數（依 selection_rules 決定）"""
    quiz_bank = load_quiz_bank()
    selection_rules = quiz_bank.get("selection_rules", {})
    return selection_rules.get("total", 5)
