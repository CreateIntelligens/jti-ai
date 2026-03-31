"""
JTI Chat API — session management, chat messages, and conversation history.
"""

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

_TZ_TAIPEI = timezone(timedelta(hours=8))

from fastapi import APIRouter, HTTPException, Depends
import logging

from app.auth import verify_admin, verify_auth
from app.models.session import SessionStep
from app.routers.tts_utils import attach_tts_message_id, register_tts_endpoints
from app.services.tts_jobs import jti_tts_job_manager as _tts_manager
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationsBySessionResponse,
    ConversationsGroupedResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteConversationRequest,
    DeleteConversationResponse,
    ExportConversationsResponse,
)
from app.services.jti.main_agent import main_agent
from app.services.jti.runtime_quiz_flow import (
    execute_quiz_start,
    extract_option_texts,
    make_quiz_tts_text,
)
from app.services.jti.tts_text import to_tts_text
from app.services.session.session_manager_factory import get_session_manager, get_conversation_logger

from app.tools.jti.quiz import get_total_questions
from app.utils import build_date_query, group_conversations_by_session
from app.services.jti.quiz_helpers import (
    _get_or_rebuild_session,
    _format_options_text,
    _pause_quiz_and_respond,
    _judge_user_choice,
    build_session_state,
)


_OPENING_MESSAGE: dict[str, str] = {
    "zh": "Hello，我是今天的活動大使Lady X，對我說「測驗」即可做「尋找命定前蓋」小遊戲，或想知道關於Ploom X加熱菸更多資訊，都歡迎和我聊聊，很樂意為您解答！",
    "en": "Hi! I'm Lady X. Got any questions, or want to take a quiz?",
}

session_manager = get_session_manager()
conversation_logger = get_conversation_logger()
logger = logging.getLogger(__name__)

runtime_router = APIRouter(prefix="/api/jti", tags=["JTI Chat"])
compat_history_router = APIRouter(
    prefix="/api/jti",
    tags=["JTI Conversations"],
    include_in_schema=False,
)
admin_history_router = APIRouter(
    prefix="/api/jti-admin/conversations",
    tags=["JTI Conversations"],
)
router = runtime_router

register_tts_endpoints(runtime_router, _tts_manager)


# === Endpoints ===

@runtime_router.post("/chat/start", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest, auth: dict = Depends(verify_auth)):
    """建立新的 JTI 對話 Session"""
    try:
        if request.previous_session_id:
            main_agent.remove_session(request.previous_session_id)
            logger.info(f"Cleaned up previous chat session: {request.previous_session_id[:8]}...")

        session = session_manager.create_session(language=request.language)
        logger.info(f"Created new session: {session.session_id} (language={request.language})")

        opening = _OPENING_MESSAGE.get(request.language, _OPENING_MESSAGE["zh"])
        return CreateSessionResponse(session_id=session.session_id, opening_message=opening)

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@runtime_router.post("/chat/message", response_model=ChatResponse)
async def chat(request: ChatRequest, auth: dict = Depends(verify_auth)):
    """
    主要對話端點

    流程設計：
    1. WELCOME/一般狀態：走 LLM（可用知識庫）
       - 使用者說「測驗」「前蓋」「玩」→ 開始測驗
       - 其他問題 → 正常回答

    2. QUIZ 狀態（有當前題目）：後端完全接管
       - 先用規則判斷使用者選 A 還是 B（明確 A/B/1/2 或選項文字）
       - 規則無法判斷時，再用 LLM 判斷
       - 判斷成功 → 呼叫 submit_answer，回覆下一題
       - 判斷失敗 → hardcode 提示 + 重問當前題
       - **不走知識庫，鎖定作答**
    """
    try:
        session = _get_or_rebuild_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        preserved_selected_questions = (
            deepcopy(session.selected_questions) if session.selected_questions else None
        )

        logger.info(f"[用戶訊息] Session: {request.session_id[:8]}... | 狀態: {session.step.value} | 訊息: '{request.message}'")

        # ========== 重新生成 / 回滾邏輯 ==========
        if request.turn_number is not None:
            deleted_count = conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            if deleted_count > 0:
                all_logs = conversation_logger.get_session_logs(request.session_id)
                logs = [l for l in all_logs if l.get("mode") == "jti"]
                if logs:
                    session = session_manager.rebuild_session_from_logs(request.session_id, logs)
                    if not session:
                        raise HTTPException(status_code=500, detail="Failed to rebuild session from logs")
                else:
                    session.step = SessionStep.WELCOME
                    session.answers = {}
                    session.current_question = None
                    session.current_q_index = 0
                    session.selected_questions = None
                    session.quiz_scores = {}
                    session.quiz_result_id = None
                    session.quiz_result = None
                    session.chat_history = []
                    session = session_manager.update_session(session)
                    logger.info(f"Session {request.session_id[:8]}... reset to initial state (no remaining logs)")

                if logs and session and preserved_selected_questions:
                    session.selected_questions = preserved_selected_questions
                    if session.step == SessionStep.QUIZ:
                        if session.current_q_index < len(preserved_selected_questions):
                            session.current_question = preserved_selected_questions[session.current_q_index]
                        else:
                            session.current_question = None
                    session = session_manager.update_session(session)

                main_agent.remove_session(request.session_id)
                logger.info(
                    f"Session {request.session_id[:8]}... rolled back to before turn {request.turn_number} "
                    f"(all_logs={len(all_logs)}, jti_logs={len(logs)}, step={session.step.value}, "
                    f"current_question={'yes' if session.current_question else 'no'})"
                )
            else:
                logger.warning(f"Failed to delete logs from turn {request.turn_number}")

        # ========== QUIZ 狀態：後端完全接管 ==========
        if session.step.value == "QUIZ" and session.current_question:
            q = session.current_question
            total_questions = get_total_questions(session.language)
            current_q_num = len(session.answers) + 1

            if request.message.strip() == "中斷":
                pause_response = ChatResponse(**(await _pause_quiz_and_respond(
                    session_id=request.session_id,
                    log_user_message=request.message,
                    session=session,
                )))
                return attach_tts_message_id(pause_response, session.language, _tts_manager)

            options_text = _format_options_text(q.get("options", []))
            logger.info(f"[測驗進度] 第 {current_q_num}/{total_questions} 題 | 題目: {q.get('text', '')[:30]}...")

            user_choice = await _judge_user_choice(request.message, q)
            logger.info(f"[答題判斷] 使用者回答: '{request.message}' -> 判定選項: {user_choice}")

            if user_choice == "PAUSE":
                pause_response = ChatResponse(**(await _pause_quiz_and_respond(
                    session_id=request.session_id,
                    log_user_message=request.message,
                    session=session,
                )))
                return attach_tts_message_id(pause_response, session.language, _tts_manager)

            if user_choice:
                from app.tools.jti.tool_executor import tool_executor
                tool_result = await tool_executor.execute("submit_answer", {
                    "session_id": request.session_id,
                    "user_choice": user_choice
                })
                tool_calls = [{"tool": "submit_answer", "args": {"user_choice": user_choice}, "result": tool_result}]

                updated_session = session_manager.get_session(request.session_id)
                logger.info(f"[答題結果] 選項: {user_choice} | 已答: {len(updated_session.answers)}/{total_questions} 題")
                if updated_session.quiz_scores:
                    scores_str = " | ".join([f"{k}:{v}" for k, v in sorted(updated_session.quiz_scores.items(), key=lambda x: -x[1])])
                    logger.info(f"[當前分數] {scores_str}")

                is_complete = tool_result.get("is_complete")
                next_q = tool_result.get("next_question") if not is_complete else None

                if is_complete:
                    response_message = tool_result.get("message", "")
                    raw_tts_text = tool_result.get("tts_text") or response_message
                    tts_text = to_tts_text(raw_tts_text, updated_session.language)

                    # 把測驗結果注入 chat_history，讓後續 LLM 對話能看到
                    main_agent.remove_session(request.session_id)
                    updated_session.chat_history.append({"role": "assistant", "content": response_message})
                    session_manager.update_session(updated_session)
                else:
                    q_num = len(updated_session.answers) + 1
                    next_options_text = _format_options_text(next_q.get("options", []))
                    if updated_session.language == "en":
                        response_message = f"Question {q_num}: {next_q.get('text', '')}\n{next_options_text}"
                    else:
                        response_message = f"第{q_num}題：{next_q.get('text', '')}\n{next_options_text}"
                    tts_text = to_tts_text(
                        make_quiz_tts_text(next_q, q_num, updated_session.language),
                        updated_session.language,
                    )

                log_result = conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=response_message,
                    tool_calls=tool_calls,
                    session_state=build_session_state(updated_session),
                    mode="jti"
                )
                final_turn_number = log_result[1] if log_result else None
                logger.info(f"QUIZ 作答成功: {request.message} -> {user_choice}")

                quiz_result = tool_result.get("quiz_result") or {}
                response_payload = ChatResponse(
                    message=response_message,
                    tts_text=tts_text,
                    options=extract_option_texts(next_q),
                    quiz_result_id=quiz_result.get("quiz_id") if is_complete else None,
                    session=updated_session.model_dump(),
                    tool_calls=[{k: v for k, v in call.items() if k != "result"} for call in tool_calls],
                    turn_number=final_turn_number,
                )
                return attach_tts_message_id(response_payload, updated_session.language, _tts_manager)
            else:
                # 無法判斷選項：hardcode 提示
                if session.language == "en":
                    hint = "Please choose one of the options!"
                    response_message = f"{hint}\n\nQuestion {current_q_num}: {q.get('text', '')}\n{options_text}"
                else:
                    hint = "請從選項中選一個喜歡的答案喔！"
                    response_message = f"{hint}\n\n第{current_q_num}題：{q.get('text', '')}\n{options_text}"

                logger.info(f"QUIZ 無法判斷選項，hardcode 提示: {request.message}")

                if request.turn_number:
                    conversation_logger.delete_turns_from(request.session_id, request.turn_number)

                log_result = conversation_logger.log_conversation(
                    session_id=request.session_id,
                    user_message=request.message,
                    agent_response=response_message,
                    tool_calls=[],
                    session_state=build_session_state(session),
                    mode="jti"
                )
                final_turn_number = log_result[1] if log_result else None

                response_payload = ChatResponse(
                    message=response_message,
                    tts_text=to_tts_text(
                        f"{hint} {make_quiz_tts_text(q, current_q_num, session.language)}",
                        session.language,
                    ),
                    options=extract_option_texts(q),
                    session=session.model_dump(),
                    tool_calls=[],
                    turn_number=final_turn_number
                )
                return attach_tts_message_id(response_payload, session.language, _tts_manager)

        # ========== 非 QUIZ 狀態 ==========
        start_keywords = [
            '測驗', '心理測驗', '前蓋測驗', '命定前蓋', '開始測驗', '玩測驗', '試試測驗',
            '再測', '重測', '重新測', '再來一次', '再測一次', '重新開始',
            '來測', '測一下', '測看看', '想測', '做測',
            '繼續測驗', '回到測驗',
            'quiz', 'start quiz', 'again', 'retry', 'redo',
        ]
        negative_keywords = ['不想', '不要', '不用', '不玩', '跳過', '算了', '不了', "don't", "dont", "no ", "not ", "skip", "pass", "never"]
        msg_lower = request.message.lower()

        has_start_intent = any(kw in msg_lower for kw in start_keywords)
        has_rejection = any(kw in msg_lower for kw in negative_keywords)
        should_start_quiz = has_start_intent and not has_rejection

        logger.info(f"[DEBUG] 測驗判斷: has_start={has_start_intent}, has_rejection={has_rejection}, should_start={should_start_quiz}")

        if should_start_quiz and session.step.value in ("DONE", "WELCOME"):
            if session.step.value == "DONE":
                session.step = SessionStep.WELCOME
                session_manager.update_session(session)
            if request.turn_number:
                conversation_logger.delete_turns_from(request.session_id, request.turn_number)
            quiz_response = await execute_quiz_start(request.session_id, user_message=request.message)
            return attach_tts_message_id(quiz_response, session.language, _tts_manager)

        # 一般對話：走 LLM
        result = await main_agent.chat(
            session_id=request.session_id,
            user_message=request.message,
        )
        logger.info(f"[AI回應] 一般對話 | {result['message'][:80]}...")

        if request.turn_number:
            conversation_logger.delete_turns_from(request.session_id, request.turn_number)

        log_result = conversation_logger.log_conversation(
            session_id=request.session_id,
            user_message=request.message,
            agent_response=result["message"],
            tool_calls=result.get("tool_calls", []),
            session_state=build_session_state(session),
            mode="jti",
            citations=result.get("citations"),
        )
        final_turn_number = log_result[1] if log_result else None

        # 非測驗回覆：tts_text 預設等同 message
        raw_tts = result.get("tts_text") or result.get("message")
        result["tts_text"] = to_tts_text(raw_tts, session.language)

        response_payload = ChatResponse(**result, turn_number=final_turn_number)
        return attach_tts_message_id(response_payload, session.language, _tts_manager)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_router.get(
    "/history",
    response_model=Union[ConversationsBySessionResponse, ConversationsGroupedResponse],
    response_model_exclude_none=True,
)
@admin_history_router.get(
    "",
    response_model=Union[ConversationsBySessionResponse, ConversationsGroupedResponse],
    response_model_exclude_none=True,
)
async def get_conversations(
    session_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    auth: dict = Depends(verify_admin),
):
    """取得對話歷史"""
    mode = "jti"
    try:
        if session_id:
            conversations = conversation_logger.get_session_logs(session_id)
            conversations = [c for c in conversations if c.get("mode") == mode]
            logger.info(f"Retrieved {len(conversations)} conversations for session {session_id}")
            return {"session_id": session_id, "mode": mode, "conversations": conversations, "total": len(conversations)}
        else:
            query = build_date_query(mode, date_from, date_to)
            session_ids, total_sessions = conversation_logger.get_paginated_session_ids(
                query=query, page=1, page_size=100000
            )
            all_conversations = conversation_logger.get_logs_for_sessions(session_ids)
            session_list = group_conversations_by_session(all_conversations)
            logger.info(f"Retrieved {len(all_conversations)} conversations across {len(session_list)} sessions (total {total_sessions})")
            return {"mode": mode, "sessions": session_list, "total_conversations": len(all_conversations), "total_sessions": total_sessions}

    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@compat_history_router.delete("/history", response_model=DeleteConversationResponse)
@admin_history_router.delete("", response_model=DeleteConversationResponse)
async def delete_conversations(request: DeleteConversationRequest, auth: dict = Depends(verify_admin)):
    """批量刪除對話紀錄"""
    total_logs = 0
    deleted_count = 0
    for sid in request.session_ids:
        total_logs += conversation_logger.delete_session_logs(sid)
        if session_manager.delete_session(sid):
            deleted_count += 1
        main_agent.remove_session(sid)

    return {"ok": True, "deleted_count": deleted_count, "deleted_logs": total_logs}


@compat_history_router.get(
    "/history/export",
    response_model=ExportConversationsResponse,
    response_model_exclude_none=True,
)
@admin_history_router.get(
    "/export",
    response_model=ExportConversationsResponse,
    response_model_exclude_none=True,
)
async def export_conversations(
    session_ids: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    auth: dict = Depends(verify_admin),
):
    """匯出對話歷史為 JSON 格式"""
    mode = "jti"
    try:
        if session_ids:
            session_id_list = [sid.strip() for sid in session_ids.split(',') if sid.strip()]
            sessions = []
            total_conversations = 0
            for session_id in session_id_list:
                conversations = conversation_logger.get_session_logs(session_id)
                conversations = [c for c in conversations if c.get("mode") == mode]
                if conversations:
                    sessions.append({
                        "session_id": session_id,
                        "conversations": conversations,
                        "first_message_time": conversations[0].get("timestamp"),
                        "total": len(conversations)
                    })
                    total_conversations += len(conversations)
            sessions.sort(key=lambda x: x["first_message_time"] or "", reverse=True)
            return {"exported_at": datetime.now(_TZ_TAIPEI).isoformat(), "mode": mode, "sessions": sessions, "total_conversations": total_conversations, "total_sessions": len(sessions)}

        if date_from or date_to:
            query = build_date_query(mode, date_from, date_to)
            sid_list, _ = conversation_logger.get_paginated_session_ids(query=query, page=1, page_size=100000)
            all_conversations = conversation_logger.get_logs_for_sessions(sid_list)
        else:
            all_conversations = conversation_logger.get_session_logs_by_mode(mode)
        session_list = group_conversations_by_session(all_conversations)
        return {"exported_at": datetime.now(_TZ_TAIPEI).isoformat(), "mode": mode, "sessions": session_list, "total_conversations": len(all_conversations), "total_sessions": len(session_list)}

    except Exception as e:
        logger.error(f"Failed to export conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
