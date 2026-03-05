"""
Tool 定義（給 Gemini Function Calling 使用）

這些定義告訴 LLM 有哪些 tools 可以呼叫
"""

from typing import List, Dict

# === Tool Definitions ===

GENERATE_QUIZ_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_quiz",
        "description": "產生色彩測驗的完整題目。這個 tool 會回傳所有題目的結構化資料。",
        "parameters": {
            "type": "object",
            "properties": {
                "quiz_id": {
                    "type": "string",
                    "description": "題庫 ID，預設為 'color_taste'",
                    "default": "color_taste"
                }
            }
        }
    }
}

GET_QUESTION_TOOL = {
    "type": "function",
    "function": {
        "name": "get_question",
        "description": "取得測驗中的單一題目。用於顯示下一題給使用者。",
        "parameters": {
            "type": "object",
            "properties": {
                "quiz_id": {
                    "type": "string",
                    "description": "題庫 ID"
                },
                "question_index": {
                    "type": "integer",
                    "description": "題目索引（0-based）"
                }
            },
            "required": ["quiz_id", "question_index"]
        }
    }
}

SUBMIT_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_answer",
        "description": "提交使用者對某題的答案。這個 tool 會更新 session 狀態。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID"
                },
                "question_id": {
                    "type": "string",
                    "description": "題目 ID（例如 'q1'）"
                },
                "option_id": {
                    "type": "string",
                    "description": "選項 ID（例如 'a' 或 'b'）"
                }
            },
            "required": ["session_id", "question_id", "option_id"]
        }
    }
}

CALCULATE_COLOR_RESULT_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_color_result",
        "description": "根據使用者的所有答案計算色系結果。這個 tool 會回傳色系與對應文案。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID"
                }
            },
            "required": ["session_id"]
        }
    }
}

# === 所有 Tools 的列表 ===

ALL_TOOLS: List[Dict] = [
    GENERATE_QUIZ_TOOL,
    GET_QUESTION_TOOL,
    SUBMIT_ANSWER_TOOL,
    CALCULATE_COLOR_RESULT_TOOL,
]


def get_all_tools() -> List[Dict]:
    """取得所有 tool 定義"""
    return ALL_TOOLS
