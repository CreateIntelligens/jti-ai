"""
Quiz helper functions extracted from app/routers/jti.py
"""

import os
import re
import logging
from typing import Optional, Any

from google import genai

from app.services.session.session_manager_factory import get_session_manager, get_conversation_logger
from app.services.jti.main_agent import main_agent

logger = logging.getLogger(__name__)

session_manager = get_session_manager()
conversation_logger = get_conversation_logger()


def _get_or_rebuild_session(session_id: str):
    """取得 session，若已過期則嘗試從 conversation logs 重建"""
    session = session_manager.get_session(session_id)
    if session:
        return session

    # 嘗試從 conversation logs 重建
    logs = conversation_logger.get_session_logs(session_id)
    jti_logs = [l for l in logs if l.get("mode") == "jti"]
    if not jti_logs:
        return None

    session = session_manager.rebuild_session_from_logs(session_id, jti_logs)
    if session:
        logger.info(f"Rebuilt expired JTI session from {len(jti_logs)} logs: {session_id[:8]}...")
        # 清除記憶體中的舊 LLM chat session（下次呼叫時會從 chat_history 自動重建）
        main_agent.remove_session(session_id)
    return session


def _format_options_text(options: list) -> str:
    labels = "ABCDE"
    lines = []
    for idx, opt in enumerate(options):
        label = labels[idx] if idx < len(labels) else str(idx + 1)
        lines.append(f"{label}. {opt.get('text', '')}")
    return "\n".join(lines)


async def _pause_quiz_and_respond(
    session_id: str,
    log_user_message: str,
    session: Any,
    turn_number_hint: Optional[int] = None
):
    """暫停測驗並回應（returns dict, caller wraps in ChatResponse）"""
    updated_session = session_manager.pause_quiz(session_id)

    # 用固定文案，不走 AI（避免 AI 從 chat history 撈出測驗中被忽略的問題來回答）
    lang = updated_session.language if updated_session else (session.language if session else "zh")
    if lang == "en":
        response_message = "Sure! The quiz is paused. You can start a new quiz anytime by saying 'start quiz'."
    else:
        response_message = "好的，測驗先暫停囉。想重新測驗的話跟我說「開始測驗」就好，或是你也可以問我其他問題。"

    # 同步到 chat history（讓 AI 恢復時知道測驗已暫停）
    main_agent._sync_history_to_db(session_id, log_user_message, response_message)

    if turn_number_hint:
        conversation_logger.delete_turns_from(session_id, turn_number_hint)

    log_result = conversation_logger.log_conversation(
        session_id=session_id,
        user_message=log_user_message,
        agent_response=response_message,
        tool_calls=[],
        session_state={
            "step": updated_session.step.value if updated_session else session.step.value,
            "answers_count": len(updated_session.answers) if updated_session else len(session.answers),
            "color_result_id": updated_session.color_result_id if updated_session else session.color_result_id,
            "current_question_id": None,
            "language": updated_session.language if updated_session else session.language,
        },
        mode="jti",
    )

    final_turn_number = log_result[1] if log_result else None

    return {
        "message": response_message,
        "session": updated_session.model_dump() if updated_session else session.model_dump(),
        "tool_calls": [],
        "turn_number": final_turn_number,
    }



async def _judge_user_choice(user_message: str, question: dict) -> Optional[str]:
    """
    先用規則判斷，判不出時用 LLM 判斷使用者選擇哪個選項

    Returns:
        "A"~"E" 或 None（無法判斷）
    """
    msg = user_message.strip()
    msg_upper = msg.upper()
    msg_lower = msg.lower()

    options = question.get("options", []) if isinstance(question, dict) else []
    labels = list("ABCDE")[: len(options)]

    # 快速判斷：明確的 A-E
    if msg_upper in labels:
        logger.info(f"[規則判斷] 明確字母: '{user_message}' -> {msg_upper}")
        return msg_upper
    # 只把「獨立字母」當作答案；避免像 "pause" 這種字串含有 A 而誤判為選 A
    label_hits = [
        label
        for label in labels
        if re.search(rf"(?<![A-Z]){label}(?![A-Z])", msg_upper)
    ]
    if len(label_hits) == 1:
        logger.info(f"[規則判斷] 獨立字母: '{user_message}' -> {label_hits[0]}")
        return label_hits[0]

    # 快速判斷：數字或中文序號
    number_map = {
        "1": 0, "一": 0, "第一": 0,
        "2": 1, "二": 1, "第二": 1,
        "3": 2, "三": 2, "第三": 2,
        "4": 3, "四": 3, "第四": 3,
        "5": 4, "五": 4, "第五": 4,
    }
    if msg in number_map and number_map[msg] < len(options):
        result = labels[number_map[msg]]
        logger.info(f"[規則判斷] 數字/序號: '{user_message}' -> {result}")
        return result
    if msg.isdigit():
        idx = int(msg) - 1
        if 0 <= idx < len(options):
            logger.info(f"[規則判斷] 純數字: '{user_message}' -> {labels[idx]}")
            return labels[idx]
    digit_hits = [d for d in ["1", "2", "3", "4", "5"] if d in msg]
    if len(digit_hits) == 1:
        idx = int(digit_hits[0]) - 1
        if 0 <= idx < len(options):
            logger.info(f"[規則判斷] 包含數字: '{user_message}' -> {labels[idx]}")
            return labels[idx]

    # 快速判斷：包含選項文字
    for idx, opt in enumerate(options):
        text = opt.get("text", "")
        if text and text.lower() in msg_lower:
            logger.info(f"[規則判斷] 匹配選項文字: '{user_message}' -> {labels[idx]} ('{text}')")
            return labels[idx]

    # 用 LLM 判斷（規則判不出時）
    logger.info(f"[LLM判斷] 規則無法判定，呼叫 LLM: '{user_message}'")
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        prompt = f"""判斷使用者意圖：作答、或是想暫停/中斷測驗。

題目：{question.get('text', '')}
{_format_options_text(options)}

使用者回覆：「{user_message}」

規則：
- 如果使用者明確說要暫停/中斷/停止/結束/退出測驗（如「暫停」「中斷」「不做了」「退出」） → 回覆 PAUSE
- 如果使用者在問產品問題或閒聊，但沒說要退出測驗 → 回覆 X（不是 PAUSE）
- 如果使用者明確選擇或傾向某選項（即使在解釋理由） → 回覆該選項的字母
- 如果無法判斷 → 回覆 X

只回覆：A 至 E、PAUSE 或 X"""

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        result = response.text.strip().upper()

        if result in labels:
            logger.info(f"[LLM判斷] 成功: '{user_message}' -> {result}")
            return result
        if result == "PAUSE":
            logger.info(f"[LLM判斷] 暫停測驗: '{user_message}' -> PAUSE")
            return "PAUSE"
        else:
            logger.info(f"[LLM判斷] 失敗/無法判斷: '{user_message}' -> {result}")
            return None

    except Exception as e:
        logger.error(f"LLM 判斷失敗: {e}")
        return None
