"""
Persona 計算工具

職責：
1. 根據答案計分
2. 映射 MBTI 類型
3. 回傳 deterministic 結果（可測試、可版本控管）

MBTI 維度：
- E (Extraversion) vs I (Introversion)
- S (Sensing) vs N (Intuition)
- T (Thinking) vs F (Feeling)
- J (Judging) vs P (Perceiving)
"""

from typing import Dict, Tuple
import logging
from app.tools.quiz import load_quiz_bank

logger = logging.getLogger(__name__)


def calculate_persona(
    quiz_id: str, answers: Dict[str, str]
) -> Dict:
    """
    計算 MBTI 類型

    Args:
        quiz_id: 題庫 ID
        answers: {question_id: option_id}

    Returns:
        {
            "persona_id": str,      # 例如 "INTJ"
            "dimension_scores": dict,  # 各維度得分
            "confidence": float     # 信心分數 (0-1)
        }
    """
    try:
        # 載入題庫
        quiz_bank = load_quiz_bank()
        quiz_set = quiz_bank["quiz_sets"].get(quiz_id)

        if not quiz_set:
            raise ValueError(f"Quiz set '{quiz_id}' not found")

        questions = quiz_set["questions"]

        # 初始化計分
        scores = {
            "E": 0,
            "I": 0,
            "S": 0,
            "N": 0,
            "T": 0,
            "F": 0,
            "J": 0,
            "P": 0,
        }

        # 計算各維度得分
        for question in questions:
            q_id = question["id"]
            if q_id not in answers:
                continue  # 跳過未回答的題目

            selected_option_id = answers[q_id]

            # 找到選項並累加分數
            for option in question["options"]:
                if option["id"] == selected_option_id:
                    for dim, score in option["score"].items():
                        scores[dim] += score
                    break

        # 判斷各維度
        mbti_type = ""
        mbti_type += "E" if scores["E"] >= scores["I"] else "I"
        mbti_type += "S" if scores["S"] >= scores["N"] else "N"
        mbti_type += "T" if scores["T"] >= scores["F"] else "F"
        mbti_type += "J" if scores["J"] >= scores["P"] else "P"

        # 計算信心分數（基於各維度的差距）
        confidence = _calculate_confidence(scores)

        result = {
            "persona_id": mbti_type,
            "dimension_scores": scores,
            "confidence": round(confidence, 2),
        }

        logger.info(
            f"Calculated persona: {mbti_type}, confidence={confidence:.2f}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to calculate persona: {e}")
        raise


def _calculate_confidence(scores: Dict[str, int]) -> float:
    """
    計算信心分數

    信心分數 = 各維度差距的平均 / 最大可能差距
    差距越大 = 傾向越明顯 = 信心越高
    """
    dimensions = [
        ("E", "I"),
        ("S", "N"),
        ("T", "F"),
        ("J", "P"),
    ]

    total_diff = 0
    max_possible_diff = 0

    for dim1, dim2 in dimensions:
        score1 = scores[dim1]
        score2 = scores[dim2]
        total_score = score1 + score2

        if total_score > 0:
            diff = abs(score1 - score2)
            total_diff += diff
            max_possible_diff += total_score

    if max_possible_diff == 0:
        return 0.0

    confidence = total_diff / max_possible_diff
    return confidence


def get_dimension_name(dimension: str) -> str:
    """取得維度中文名稱"""
    dimension_names = {
        "E": "外向",
        "I": "內向",
        "S": "實感",
        "N": "直覺",
        "T": "思考",
        "F": "情感",
        "J": "判斷",
        "P": "感知",
    }
    return dimension_names.get(dimension, dimension)


def get_mbti_description(mbti_type: str) -> str:
    """取得 MBTI 類型描述"""
    descriptions = {
        "INTJ": "建築師 - 富有想像力和戰略性的思考者",
        "INTP": "邏輯學家 - 創新的發明家",
        "ENTJ": "指揮官 - 大膽、富有想像力的強大領導者",
        "ENTP": "辯論家 - 聰明好奇的思想家",
        "INFJ": "提倡者 - 安靜而神秘的理想主義者",
        "INFP": "調停者 - 詩意、善良和利他的人",
        "ENFJ": "主人公 - 魅力四射、鼓舞人心的領導者",
        "ENFP": "競選者 - 熱情、有創造力和社交能力強的自由精神",
        "ISTJ": "物流師 - 實用且注重事實的個人",
        "ISFJ": "守衛者 - 非常專注和溫暖的保護者",
        "ESTJ": "總經理 - 出色的管理者",
        "ESFJ": "執政官 - 極有同情心、受歡迎的人",
        "ISTP": "鑒賞家 - 大膽而實際的實驗者",
        "ISFP": "探險家 - 靈活、有魅力的藝術家",
        "ESTP": "企業家 - 精明、善於感知和充滿活力的人",
        "ESFP": "表演者 - 自發的、充滿活力和熱情的表演者",
    }
    return descriptions.get(mbti_type, f"{mbti_type} 類型")
