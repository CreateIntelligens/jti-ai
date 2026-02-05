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

COLOR_RESULTS_PATH = Path("data/color_results.json")
_color_results_cache: Optional[Dict[str, Any]] = None


def load_color_results() -> Dict[str, Any]:
    """載入色彩結果對照表"""
    global _color_results_cache
    if _color_results_cache is None:
        with open(COLOR_RESULTS_PATH, "r", encoding="utf-8") as f:
            _color_results_cache = json.load(f)
    return _color_results_cache


def calculate_color_result(answers: Dict[str, str]) -> Dict[str, Any]:
    """
    計算色系結果

    Args:
        answers: {question_id: option_id}

    Returns:
        {
            "color_id": str,
            "color_scores": dict,
            "result": dict | None,
            "tie_breaker_priority": list
        }
    """
    quiz_bank = load_quiz_bank()
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

    results = load_color_results()
    result = results.get(color_id)

    logger.info("Calculated color result: %s", color_id)
    return {
        "color_id": color_id,
        "color_scores": scores,
        "result": result,
        "tie_breaker_priority": tie_breaker,
    }
