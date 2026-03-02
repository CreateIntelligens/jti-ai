"""
色彩測驗結果計算工具

職責：
1. 根據答案計分
2. 依平手優先順序決定色系
3. 回傳結果內容（文案與推薦色）
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from app.tools.quiz import load_quiz_bank

logger = logging.getLogger(__name__)

COLOR_RESULTS_PATHS = {
    "zh": Path("data/color_results.json"),
    "en": Path("data/color_results_en.json"),
}
_color_results_cache: Dict[str, Dict[str, Any]] = {}


def load_color_results(language: str = "zh") -> Dict[str, Any]:
    """載入色彩結果對照表（MongoDB-first, JSON fallback）"""
    global _color_results_cache
    if language not in _color_results_cache:
        # MongoDB first
        try:
            from app.services.color_results_store import get_color_results_store
            store = get_color_results_store()
            results = store.get_all_results(language)
            if results:
                _color_results_cache[language] = results
                return _color_results_cache[language]
        except Exception as e:
            logger.warning("MongoDB color results load failed, falling back to JSON: %s", e)

        # JSON fallback
        path = COLOR_RESULTS_PATHS.get(language, COLOR_RESULTS_PATHS["zh"])
        with open(path, "r", encoding="utf-8") as f:
            _color_results_cache[language] = json.load(f)
    return _color_results_cache[language]


def invalidate_color_results_cache(language: str = "zh"):
    """Clear color results cache for a language (call after CRUD operations)."""
    _color_results_cache.pop(language, None)


def calculate_color_result(answers: Dict[str, str], language: str = "zh") -> Dict[str, Any]:
    """
    計算色系結果

    Args:
        answers: {question_id: option_id}
        language: language code

    Returns:
        {
            "color_id": str,
            "color_scores": dict,
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
            "color_id": None,
            "color_scores": {},
            "result": None,
            "tie_breaker_priority": tie_breaker,
        }

    max_score = max(scores.values())
    tied = [dim for dim, value in scores.items() if value == max_score]

    color_id = None
    for dim in tie_breaker:
        if dim in tied:
            color_id = dim
            break
    if color_id is None and tied:
        color_id = tied[0]

    results = load_color_results(language)
    result = results.get(color_id)

    logger.info("Calculated color result: %s", color_id)
    return {
        "color_id": color_id,
        "color_scores": scores,
        "result": result,
        "tie_breaker_priority": tie_breaker,
    }
