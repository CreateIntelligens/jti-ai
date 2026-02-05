"""
Tool 執行器

當 LLM 呼叫 tool 時，這裡負責執行實際邏輯並回傳結果
"""

from typing import Dict, Any, Optional
import logging
from google.genai import types
from app.tools.quiz import (
    generate_quiz,
    get_question as quiz_get_question,
    get_total_questions,
    generate_random_quiz,
    get_question_from_selected,
)
from app.tools.color_results import calculate_color_result as calc_color_result
from app.services.session_manager import session_manager

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Tool 執行器"""

    def __init__(self):
        self.tool_map = {
            "quiz_response": self._execute_quiz_response,
            "start_quiz": self._execute_start_quiz,
            "get_question": self._execute_get_question,
            "submit_answer": self._execute_submit_answer,
            "calculate_color_result": self._execute_calculate_color_result,
        }

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict:
        """執行 tool"""
        if tool_name not in self.tool_map:
            logger.error(f"Unknown tool: {tool_name}")
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            logger.info(f"Executing tool: {tool_name}, args: {arguments}")
            result = await self.tool_map[tool_name](arguments)
            logger.info(f"Tool result: {tool_name} -> success")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {e}")
            return {"error": str(e)}

    @staticmethod
    def _get_option_labels(options: list) -> list:
        labels = "ABCDE"
        return list(labels[: len(options)])

    def _format_options(self, options: list) -> str:
        labels = self._get_option_labels(options)
        return "\n".join(
            f"{labels[i]}. {opt.get('text', '')}"
            for i, opt in enumerate(options)
        )

    def _map_user_choice_to_option_id(self, user_choice: str, options: list) -> Optional[str]:
        if not user_choice or not options:
            return None

        normalized = user_choice.strip().upper()
        labels = self._get_option_labels(options)

        if normalized in labels:
            return options[labels.index(normalized)].get("id")

        number_map = {
            "1": 0, "一": 0, "第一": 0,
            "2": 1, "二": 1, "第二": 1,
            "3": 2, "三": 2, "第三": 2,
            "4": 3, "四": 3, "第四": 3,
            "5": 4, "五": 4, "第五": 4,
        }
        if normalized in number_map and number_map[normalized] < len(options):
            return options[number_map[normalized]].get("id")

        if normalized.isdigit():
            idx = int(normalized) - 1
            if 0 <= idx < len(options):
                return options[idx].get("id")

        for opt in options:
            text = opt.get("text", "")
            if text and text in user_choice:
                return opt.get("id")

        return None

    def _format_question_text(self, question: Dict, index: int, language: str) -> str:
        options_text = self._format_options(question.get("options", []))
        if language == "en":
            return f"Question {index}: {question.get('text', '')}\n{options_text}"
        return f"第{index}題：{question.get('text', '')}\n{options_text}"

    # === Tool 實作 ===

    async def _execute_quiz_response(self, args: Dict) -> Dict:
        """統一處理測驗互動（開始測驗 或 回答題目）"""
        session_id = args.get("session_id")
        action = args.get("action")
        user_choice = args.get("user_choice", "")

        if not session_id or not action:
            return {"error": "Missing session_id or action"}

        session = session_manager.get_session(session_id)
        if not session:
            return {"error": "Session not found"}

        # 開始測驗
        if action == "start":
            return await self._execute_start_quiz({"session_id": session_id})

        # 回答題目
        if action == "answer":
            if not session.current_question:
                return {"error": "沒有進行中的題目"}

            # 判斷選項
            question = session.current_question
            option_id = self._map_user_choice_to_option_id(
                user_choice, question.get("options", [])
            )
            if not option_id:
                labels = self._get_option_labels(question.get("options", []))
                return {"error": f"無效的選擇：{user_choice}，請選擇 {' / '.join(labels)}"}

            question_id = question.get("id")

            # 提交答案（包含自動計算色系結果和問下一題的邏輯）
            result = await self._execute_submit_answer({
                "session_id": session_id,
                "question_id": question_id,
                "option_id": option_id
            })

            return result

        return {"error": f"Unknown action: {action}"}

    async def _execute_start_quiz(self, args: Dict) -> Dict:
        """開始測驗"""
        session_id = args.get("session_id")

        if not session_id:
            return {"error": "Missing session_id"}

        # 取得 session 語言設定
        session = session_manager.get_session(session_id)
        language = session.language if session else "zh"

        quiz_id = session.quiz_id if session else "color_taste"
        total_questions = get_total_questions(quiz_id)

        # 隨機抽選題目（依 selection_rules）
        selected_questions = generate_random_quiz(quiz_id, language)

        # 重置測驗狀態並保存選中的題目
        session = session_manager.start_quiz(session_id, selected_questions)

        if session is None:
            return {"error": "Session not found"}

        # 取得第一題
        question = selected_questions[0]

        # 保存當前題目到 session
        session_manager.set_current_question(session_id, question)

        # 根據語言生成訊息
        message = f"\n{self._format_question_text(question, 1, language)}"

        return {
            "success": True,
            "message": message,
            "current_question": question,
            "total_questions": total_questions,
            "progress": 0
        }

    async def _execute_get_question(self, args: Dict) -> Dict:
        """取得當前題目"""
        session_id = args.get("session_id")

        if not session_id:
            return {"error": "Missing session_id"}

        session = session_manager.get_session(session_id)

        if session is None:
            return {"error": "Session not found"}

        # 從 session 中選中的題目列表取得當前題目
        if session.selected_questions:
            question = get_question_from_selected(session.selected_questions, session.current_q_index)
        else:
            question = None

        total = get_total_questions(session.quiz_id)

        if question is None:
            # 已經完成所有題目
            return {
                "complete": True,
                "message": "所有題目已回答完畢",
                "total_answered": len(session.answers)
            }

        return {
            "question": question,
            "current_index": session.current_q_index,
            "total_questions": total,
            "progress": f"{session.current_q_index + 1} / {total}"
        }

    async def _execute_submit_answer(self, args: Dict) -> Dict:
        """提交答案"""
        session_id = args.get("session_id")

        # 檢查是否來自 LLM（有 user_choice）還是內部呼叫（有 question_id + option_id）
        user_choice = args.get("user_choice", "")
        question_id = args.get("question_id")
        option_id = args.get("option_id")

        # 如果有 user_choice，從 session 取得當前題目
        if user_choice:
            session = session_manager.get_session(session_id)
            if not session or not session.current_question:
                return {"error": "沒有進行中的題目"}

            question = session.current_question
            option_id = self._map_user_choice_to_option_id(
                user_choice, question.get("options", [])
            )
            if not option_id:
                labels = self._get_option_labels(question.get("options", []))
                return {"error": f"user_choice 必須是 {' / '.join(labels)}，收到：{user_choice}"}

            question_id = question.get("id")

        # 驗證必要參數
        if not all([session_id, question_id, option_id]):
            return {"error": "Missing required parameters"}

        # 更新 session
        session = session_manager.submit_answer(
            session_id, question_id, option_id
        )

        if session is None:
            return {"error": "Session not found or invalid state"}

        # 檢查是否完成測驗
        total_questions = get_total_questions(session.quiz_id)
        is_complete = session.is_quiz_complete(total_questions)

        logger.info(f"Answer submitted: Q{question_id}={option_id}, answered={len(session.answers)}/{total_questions}, complete={is_complete}")

        result = {
            "success": True,
            "answered": question_id,
            "selected": option_id,
            "current_index": session.current_q_index,
            "total_questions": total_questions,
            "is_complete": is_complete,
        }

        # 如果還沒完成，附上下一題並保存到 session
        if not is_complete:
            # 取得剛回答的題目資訊（用於評論）
            answered_question = session.selected_questions[session.current_q_index - 1] if session.selected_questions else None
            answered_option_text = ""
            if answered_question:
                matched_option = next(
                    (opt for opt in answered_question.get("options", []) if opt.get("id") == option_id),
                    None,
                )
                answered_option_text = matched_option.get("text", "") if matched_option else ""

            # 從 session 中選中的題目列表取得下一題
            if session.selected_questions:
                next_question = get_question_from_selected(session.selected_questions, session.current_q_index)
            else:
                # 向後相容：如果沒有 selected_questions，使用舊邏輯
                next_question = quiz_get_question(session.quiz_id, session.current_q_index)

            result["next_question"] = next_question

            next_question_text = self._format_question_text(
                next_question, session.current_q_index + 1, session.language
            )

            # 根據語言生成指令
            if session.language == "en":
                result["instruction_for_llm"] = f"""User chose "{answered_option_text}". Give a brief comment (5-10 words) about this choice, then ask the next question.

Comment examples:
- "Loves recharging alone."
- "Very creative type."
- "Practical minded."
- "Values feelings."

Next question to ask:
{next_question_text}

Format:
- Keep A. B. C. D. E. labels before each option
- Don't say "Thank you for your answer"
- Keep comments under 10 words"""
            else:
                result["instruction_for_llm"] = f"""使用者選擇了「{answered_option_text}」，請用一句話簡短評論這個選擇（5-10字），然後問下一題。

評論範例：
- 「喜歡獨處充電的人」
- 「很有創意的類型」
- 「務實派的你」
- 「重視感受的人」

必須問的下一題：
{next_question_text}

格式要求：
- 選項前面必須保留 A. B. C. D. E. 的編號
- 不要說「好的，謝謝您的回答」
- 評論要簡短，不要超過 10 個字"""
            session_manager.set_current_question(session_id, next_question)
        else:
            # 完成測驗，立即計算色系結果
            logger.info("測驗完成，自動執行 calculate_color_result")
            session_manager.set_current_question(session_id, None)

            color_result = await self._execute_calculate_color_result({"session_id": session_id})

            if "error" in color_result:
                result["message"] = f"測驗完成，但計算結果時發生錯誤：{color_result['error']}"
            else:
                result["message"] = color_result.get("message", "計算完成")
                result["color_result"] = color_result
                result["instruction_for_llm"] = (
                    "使用者已完成色彩測驗，請用親切溫柔的語氣回覆，"
                    "並完整保留以下文案內容：\n"
                    f"{result['message']}"
                )

        return result

    async def _execute_calculate_color_result(self, args: Dict) -> Dict:
        """計算色系結果"""
        session_id = args.get("session_id")

        if not session_id:
            return {"error": "Missing session_id"}

        session = session_manager.get_session(session_id)

        if session is None:
            return {"error": "Session not found"}

        # 進入計分狀態
        session_manager.start_scoring(session_id)

        # 計算色系
        result = calc_color_result(session.answers)
        color_id = result.get("color_id")
        color_scores = result.get("color_scores", {})
        color_info = result.get("result")

        # 更新 session
        if color_id:
            session_manager.complete_scoring(
                session_id,
                color_result_id=color_id,
                scores=color_scores,
                color_result=color_info,
            )

        # 組合文案（TTS 使用）
        if color_info:
            title = color_info.get("title", "")
            color_name = color_info.get("color_name", color_id or "")
            description = color_info.get("description", "")
            message = f"你的色系是{color_name}，{title}。{description}".strip()
        else:
            message = "測驗完成，但找不到對應的色系結果。"

        if len(message) > 200:
            message = message[:200]

        return {
            "color_id": color_id,
            "color_scores": color_scores,
            "result": color_info,
            "message": message,
        }

# 全域實例
tool_executor = ToolExecutor()
