"""
Quiz 工具：產生「尋找命定前蓋」測驗題目

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

from app.services.quiz.config import JTI_STORE_NAME

logger = logging.getLogger(__name__)

# 載入題庫（支援中英文）
QUIZ_BANK_PATHS = {
    "zh": Path("data/jti/quiz_bank_zh.json"),
    "en": Path("data/jti/quiz_bank_en.json"),
}
quiz_data_cache = {}


def load_quiz_bank(language: str = "zh", store_name: str = JTI_STORE_NAME):
    """載入題庫（MongoDB-first, JSON fallback）"""
    global quiz_data_cache
    cache_key = (store_name, language)
    if cache_key not in quiz_data_cache:
        # MongoDB first
        try:
            from app.services.jti.quiz_bank_store import get_quiz_bank_store
            store = get_quiz_bank_store()
            bank = store.get_full_bank(language, store_name=store_name)
            if bank and bank.get("questions"):
                quiz_data_cache[cache_key] = bank
                return quiz_data_cache[cache_key]
        except Exception as e:
            logger.warning("MongoDB quiz bank load failed, falling back to JSON: %s", e)

        # JSON fallback only for __jti__
        if store_name == JTI_STORE_NAME:
            path = QUIZ_BANK_PATHS.get(language, QUIZ_BANK_PATHS["zh"])
            with open(path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                quiz_data_cache[cache_key] = next(iter(raw_data["quiz_sets"].values()))
        else:
            # If not __jti__, and mongodb has no data, return empty template bank
            quiz_data_cache[cache_key] = {
                "title": "",
                "description": "",
                "total_questions": 4,
                "questions": [],
                "dimensions": ["analyst", "diplomat", "guardian", "explorer"],
                "tie_breaker_priority": ["analyst", "diplomat", "guardian", "explorer"],
                "selection_rules": {"total": 4},
            }
    return quiz_data_cache[cache_key]


def invalidate_quiz_cache(language: str = "zh", store_name: str = JTI_STORE_NAME):
    """Clear quiz data cache for a language (call after CRUD operations)."""
    quiz_data_cache.pop((store_name, language), None)


def generate_random_quiz(language: str = "zh", store_name: str = JTI_STORE_NAME) -> List[Dict]:
    """
    產生隨機測驗題目

    策略：
    - 依 selection_rules.total 從題庫中隨機抽題
    - 總題數由 selection_rules.total 決定（預設 4 題）
    """
    try:
        quiz_bank = load_quiz_bank(language, store_name=store_name)
        all_questions = quiz_bank.get("questions", [])
        selection_rules = quiz_bank.get("selection_rules", {})
        total_questions = selection_rules.get("total", 4)
        if not all_questions:
            return []

        selected = random.sample(all_questions, k=min(total_questions, len(all_questions)))

        logger.info(
            "Generated random quiz (%s, %s), selected %s questions: %s",
            store_name,
            language,
            len(selected),
            [q.get("id") for q in selected],
        )
        return selected

    except Exception as e:
        logger.error(f"Failed to generate random quiz: {e}")
        raise


def generate_quiz(language: str = "zh", store_name: str = JTI_STORE_NAME) -> Dict:
    """產生測驗題目"""
    try:
        quiz_bank = load_quiz_bank(language, store_name=store_name)
        questions = generate_random_quiz(language, store_name=store_name)
        result = {
            "name": quiz_bank.get("title", ""),
            "description": quiz_bank.get("description", ""),
            "total_questions": len(questions),
            "questions": questions,
        }
        logger.info(f"Generated quiz ({store_name}, {language}), {len(questions)} questions")
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


def complete_selected_questions(
    selected_questions: List[Dict],
    language: str = "zh",
    store_name: str = JTI_STORE_NAME,
) -> List[Dict]:
    """Deterministically fill missing quiz questions when selected list is incomplete."""
    if not selected_questions:
        return selected_questions

    try:
        quiz_bank = load_quiz_bank(language, store_name=store_name)
        all_questions = quiz_bank.get("questions", [])
        selection_rules = quiz_bank.get("selection_rules", {})
        total_questions = selection_rules.get("total", 4)

        completed: List[Dict] = []
        used_ids = set()
        for question in selected_questions:
            qid = question.get("id") if isinstance(question, dict) else None
            if qid and qid not in used_ids:
                completed.append(question)
                used_ids.add(qid)

        if len(completed) >= total_questions:
            return completed[:total_questions]

        remaining = sorted(
            (q for q in all_questions if q.get("id") not in used_ids),
            key=lambda q: q.get("id", ""),
        )

        while len(completed) < total_questions and remaining:
            picked = remaining.pop(0)
            completed.append(picked)
            used_ids.add(picked["id"])

        logger.warning(
            "Recovered incomplete selected_questions: %s -> %s (%s, %s)",
            len(selected_questions),
            len(completed),
            store_name,
            language,
        )
        return completed

    except Exception as e:
        logger.error(f"Failed to complete selected questions: {e}")
        return selected_questions


def get_total_questions(language: str = "zh", store_name: str = JTI_STORE_NAME) -> int:
    """取得題庫總題數（依 selection_rules 決定）"""
    quiz_bank = load_quiz_bank(language, store_name=store_name)
    selection_rules = quiz_bank.get("selection_rules", {})
    return selection_rules.get("total", 4)
