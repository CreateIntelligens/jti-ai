"""
Tool 執行器

當 LLM 呼叫 tool 時，這裡負責執行實際邏輯並回傳結果
"""

from typing import Dict, Any
import logging
from google.genai import types
from app.tools.quiz import generate_quiz, get_question as quiz_get_question, get_total_questions, generate_random_quiz, get_question_from_selected
from app.tools.persona import calculate_persona as calc_persona, get_mbti_description
from app.tools.products import recommend_products as rec_products
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
            "calculate_persona": self._execute_calculate_persona,
            "recommend_products": self._execute_recommend_products,
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

    # === Tool 實作 ===

    async def _execute_quiz_response(self, args: Dict) -> Dict:
        """統一處理測驗互動（開始測驗 或 回答題目）"""
        session_id = args.get("session_id")
        action = args.get("action")
        user_choice = args.get("user_choice", "").upper()

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
            if user_choice not in ["A", "B"]:
                return {"error": f"無效的選擇：{user_choice}，請選擇 A 或 B"}

            option_id = "a" if user_choice == "A" else "b"
            question_id = session.current_question.get("id")

            # 提交答案（包含自動計算 persona 和問下一題的邏輯）
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

        # 隨機抽選 5 題（每個維度 1 題 + 額外 1 題）
        selected_questions = generate_random_quiz("mbti_quick")

        # 重置測驗狀態並保存選中的題目
        session = session_manager.start_quiz(session_id, selected_questions)

        if session is None:
            return {"error": "Session not found"}

        # 取得第一題
        question = selected_questions[0]

        # 保存當前題目到 session
        session_manager.set_current_question(session_id, question)

        return {
            "success": True,
            "message": f"\n第1題：{question['text']}\nA. {question['options'][0]['text']}\nB. {question['options'][1]['text']}",
            "current_question": question,
            "total_questions": 5,
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

        total = 5

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
        user_choice = args.get("user_choice", "").upper()
        question_id = args.get("question_id")
        option_id = args.get("option_id")

        # 如果有 user_choice，從 session 取得當前題目
        if user_choice:
            if user_choice not in ["A", "B"]:
                return {"error": f"user_choice 必須是 A 或 B，收到：{user_choice}"}

            session = session_manager.get_session(session_id)
            if not session or not session.current_question:
                return {"error": "沒有進行中的題目"}

            question_id = session.current_question.get("id")
            option_id = "a" if user_choice == "A" else "b"

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
        total_questions = 5
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
                opt_index = 0 if option_id == "a" else 1
                answered_option_text = answered_question['options'][opt_index]['text']

            # 從 session 中選中的題目列表取得下一題
            if session.selected_questions:
                next_question = get_question_from_selected(session.selected_questions, session.current_q_index)
            else:
                # 向後相容：如果沒有 selected_questions，使用舊邏輯
                next_question = quiz_get_question(session.quiz_id, session.current_q_index)

            result["next_question"] = next_question
            # 讓 LLM 簡短評論上一題答案，然後問下一題
            result["instruction_for_llm"] = f"""使用者選擇了「{answered_option_text}」，請用一句話簡短評論這個選擇（5-10字），然後問下一題。

評論範例：
- 「喜歡獨處充電的人～」
- 「很有創意的類型！」
- 「務實派的你～」
- 「重視感受的人呢」

必須問的下一題：
第{session.current_q_index + 1}題：{next_question['text']}
A. {next_question['options'][0]['text']}
B. {next_question['options'][1]['text']}

禁止事項：
- 不要問「請選擇 A 還是 B」
- 不要說「好的，謝謝您的回答」
- 評論要簡短，不要超過 10 個字"""
            session_manager.set_current_question(session_id, next_question)
        else:
            # 完成測驗，立即計算 MBTI 類型
            logger.info(f"測驗完成，自動執行 calculate_persona")
            session_manager.set_current_question(session_id, None)
            
            # 自動呼叫 calculate_persona
            persona_result = await self._execute_calculate_persona({"session_id": session_id})
            
            if "error" in persona_result:
                result["message"] = f"測驗完成，但計算結果時發生錯誤：{persona_result['error']}"
            else:
                result["message"] = persona_result.get("message", "計算完成")
                result["persona_result"] = persona_result

        return result

    async def _execute_calculate_persona(self, args: Dict) -> Dict:
        """計算 persona"""
        session_id = args.get("session_id")

        if not session_id:
            return {"error": "Missing session_id"}

        session = session_manager.get_session(session_id)

        if session is None:
            return {"error": "Session not found"}

        # 進入計分狀態
        session_manager.start_scoring(session_id)

        # 計算 MBTI
        result = calc_persona(session.quiz_id, session.answers)

        # 取得描述
        description = get_mbti_description(result["persona_id"])

        # 更新 session
        session_manager.complete_scoring(
            session_id,
            persona=result["persona_id"],
            scores=result["dimension_scores"],
        )

        return {
            "persona_id": result["persona_id"],
            "description": description,
            "dimension_scores": result["dimension_scores"],
            "confidence": result["confidence"],
            "message": f"恭喜！你的 MBTI 類型是 {result['persona_id']}。\n\n{description}"
        }

    async def _execute_recommend_products(self, args: Dict) -> Dict:
        """推薦商品"""
        session_id = args.get("session_id")
        max_results = args.get("max_results", 3)

        if not session_id:
            return {"error": "Missing session_id"}

        session = session_manager.get_session(session_id)

        if session is None:
            return {"error": "Session not found"}

        if session.persona is None:
            return {"error": "請先完成 MBTI 測驗"}

        # 推薦商品
        products = rec_products(
            persona=session.persona,
            max_results=max_results
        )

        # 更新 session
        session_manager.save_recommendations(session_id, products)

        # 構建商品訊息
        product_messages = []
        for i, prod in enumerate(products, 1):
            product_messages.append(f"{i}. {prod.get('name', '商品')} - {prod.get('description', '暫無描述')}")

        products_text = "\n".join(product_messages) if product_messages else "暫無推薦商品"

        return {
            "persona": session.persona,
            "products": products,
            "total_results": len(products),
            "message": f"根據你的 MBTI 類型 {session.persona}，我為你推薦了以下商品：\n\n{products_text}"
        }

# 全域實例
tool_executor = ToolExecutor()
