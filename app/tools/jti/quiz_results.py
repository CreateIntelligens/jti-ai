"""
「尋找命定前蓋」測驗結果計算工具

職責：
1. 根據答案計分
2. 依平手優先順序決定結果
3. 回傳結果內容（文案與推薦色）
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from app.tools.jti.quiz import load_quiz_bank

logger = logging.getLogger(__name__)

QUIZ_RESULTS_PATHS = {
    "zh": Path("data/quiz_results.json"),
    "en": Path("data/quiz_results_en.json"),
}
_quiz_results_cache: Dict[str, Dict[str, Any]] = {}


def load_quiz_results(language: str = "zh") -> Dict[str, Any]:
    """載入測驗結果對照表（MongoDB-first, JSON fallback）"""
    global _quiz_results_cache
    if language not in _quiz_results_cache:
        # MongoDB first
        try:
            from app.services.jti.quiz_results_store import get_quiz_results_store
            store = get_quiz_results_store()
            results = store.get_all_results(language)
            if results:
                _quiz_results_cache[language] = results
                return _quiz_results_cache[language]
        except Exception as e:
            logger.warning("MongoDB quiz results load failed, falling back to JSON: %s", e)

        # JSON fallback
        path = QUIZ_RESULTS_PATHS.get(language, QUIZ_RESULTS_PATHS["zh"])
        with open(path, "r", encoding="utf-8") as f:
            _quiz_results_cache[language] = json.load(f)
    return _quiz_results_cache[language]


def invalidate_quiz_results_cache(language: str = "zh"):
    """Clear quiz results cache for a language (call after CRUD operations)."""
    _quiz_results_cache.pop(language, None)


def calculate_quiz_result(answers: Dict[str, str], language: str = "zh") -> Dict[str, Any]:
    """
    計算測驗結果

    Args:
        answers: {question_id: option_id}
        language: language code

    Returns:
        {
            "quiz_id": str,
            "quiz_scores": dict,
            "result": dict | None,
            "tie_breaker_priority": list
        }
    """
    quiz_bank = load_quiz_bank(language)
    questions = quiz_bank.get("questions", [])
    dimensions = quiz_bank.get("dimensions", [])
    tie_breaker = quiz_bank.get("tie_breaker_priority", list(dimensions))

    scores: Dict[str, int] = {dim: 0 for dim in dimensions}

    for question in questions:
        q_id = question.get("id")
        if q_id not in answers:
            continue

        option_id = answers[q_id]
        option = next(
            (opt for opt in question.get("options", []) if opt.get("id") == option_id),
            None,
        )
        if not option:
            continue

        for dim, score in option.get("score", {}).items():
            scores[dim] = scores.get(dim, 0) + score

    if not scores:
        return {
            "quiz_id": None,
            "quiz_scores": {},
            "result": None,
            "tie_breaker_priority": tie_breaker,
        }

    max_score = max(scores.values())
    tied = [dim for dim, value in scores.items() if value == max_score]

    quiz_id = None
    for dim in tie_breaker:
        if dim in tied:
            quiz_id = dim
            break
    if quiz_id is None and tied:
        quiz_id = tied[0]

    results = load_quiz_results(language)
    result = results.get(quiz_id)

    logger.info("Calculated quiz result: %s", quiz_id)
    return {
        "quiz_id": quiz_id,
        "quiz_scores": scores,
        "result": result,
        "tie_breaker_priority": tie_breaker,
    }
