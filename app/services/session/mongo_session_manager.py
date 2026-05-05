"""
MongoDB Session 管理服務

職責：
1. 在 MongoDB 中進行 Session CRUD
2. 狀態機管理
3. 支持查詢和分析
"""

from typing import Dict, Optional, List, Any
from datetime import datetime

from app.models.session import Session, SessionStep
from app.services.mongo_client import get_mongo_db
from app.tools.jti.quiz import complete_selected_questions, get_total_questions
from .session_state_mixin import SessionStateMixin
import logging

logger = logging.getLogger(__name__)


def _get_log_snapshot(log: Dict[str, Any]) -> Dict[str, Any]:
    """Extract session snapshot or state from a log entry."""
    return log.get("session_snapshot") or log.get("session_state") or {}


def _longest_list(*candidates: Any) -> List[Any]:
    """Return the longest list among the given candidates."""
    longest: List[Any] = []
    for candidate in candidates:
        if isinstance(candidate, list) and len(candidate) > len(longest):
            longest = candidate
    return longest


def _extract_quiz_state_from_logs(logs: List[Dict]) -> Dict[str, Any]:
    """Extract chat history and quiz state collected from conversation logs."""
    answers = {}
    selected_questions = []
    quiz_scores = {}
    quiz_result = None
    chat_history = []

    for log in logs:
        if user_msg := log.get("user_message"):
            chat_history.append({"role": "user", "content": user_msg})
        if agent_resp := log.get("agent_response"):
            chat_history.append({"role": "assistant", "content": agent_resp})

        for tool_call in log.get("tool_calls", []):
            tool = tool_call.get("tool") or tool_call.get("tool_name")
            result = tool_call.get("result", {})

            if tool == "start_quiz" and (q := result.get("current_question")):
                selected_questions.append(q)
            elif tool == "submit_answer":
                if result.get("success"):
                    q_id = result.get("answered")
                    opt_id = result.get("selected")
                    if q_id and opt_id:
                        answers[q_id] = opt_id
                if next_q := result.get("next_question"):
                    selected_questions.append(next_q)
                if completed_result := result.get("quiz_result"):
                    quiz_scores = completed_result.get("quiz_scores", {})
                    quiz_result = completed_result.get("result")

    snapshot = _get_log_snapshot(logs[-1])
    return {
        "answers": answers,
        "selected_questions": selected_questions,
        "quiz_scores": quiz_scores,
        "quiz_result": quiz_result,
        "quiz_result_id": snapshot.get("quiz_result_id"),
        "chat_history": chat_history,
        "snapshot": snapshot,
        "step": snapshot.get("step", "WELCOME"),
    }


def _resolve_session_language(logs: List[Dict], default: str) -> str:
    """Infer rebuilt session language from the last log snapshot.

    Mongo find_one may return non-str values (e.g. MagicMock in tests, or a
    legacy doc with a missing/null language); guard at every layer.
    """
    snapshot = _get_log_snapshot(logs[-1])
    language = snapshot.get("language")
    if isinstance(language, str):
        return language
    return default if isinstance(default, str) else "zh"


def _reconcile_selected_questions(
    selected_questions: List[Dict[str, Any]],
    *,
    snapshot: Dict[str, Any],
    existing_selected_questions: Optional[List[Dict[str, Any]]],
    language: str,
) -> List[Dict[str, Any]]:
    """Use the most complete selected_questions source and fill missing tail items."""
    reconciled = _longest_list(
        selected_questions,
        snapshot.get("selected_questions"),
        existing_selected_questions,
    )

    if reconciled:
        total_questions = get_total_questions(language)
        if len(reconciled) < total_questions:
            reconciled = complete_selected_questions(reconciled, language=language)

    return reconciled


def _resolve_rebuilt_current_question(
    session_id: str,
    step: str,
    selected_questions: List[Dict[str, Any]],
    current_q_index: int,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Resolve rebuilt current_question, degrading invalid QUIZ state to WELCOME."""
    if step != "QUIZ":
        return step, None

    if selected_questions and current_q_index < len(selected_questions):
        return step, selected_questions[current_q_index]

    reason = (
        "no selected_questions"
        if not selected_questions
        else f"selected_questions ({len(selected_questions)}) < current_q_index ({current_q_index})"
    )
    logger.warning(f"Rebuilding session {session_id[:8]}...: {reason}, degrading to WELCOME")
    return "WELCOME", None


def _persist_rebuilt_session(sessions_collection, session_id: str, session: Session) -> None:
    """Write rebuilt session back to MongoDB."""
    session_dict = session.model_dump(mode="json")
    session_dict["created_at"] = datetime.now()
    session_dict["updated_at"] = datetime.now()
    sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": session_dict},
        upsert=True,
    )


class MongoSessionManager(SessionStateMixin):
    """MongoDB Session 管理器"""

    def __init__(self, db_name: str):
        self.db = get_mongo_db(db_name)
        self.sessions_collection = self.db["sessions"]
        self._pending: Dict[str, Session] = {}  # lazy write 暫存，尚未寫入 MongoDB

    def create_session(self, language: str = "zh") -> Session:
        """Create new session (write to MongoDB, fallback to pending memory)."""
        session = Session(language=language)
        try:
            now = datetime.now()
            doc = {**session.model_dump(mode="json"), "created_at": now, "updated_at": now}
            self.sessions_collection.update_one({"session_id": session.session_id}, {"$set": doc}, upsert=True)
            logger.info(f"Created session in MongoDB: {session.session_id}")
        except Exception as e:
            self._pending[session.session_id] = session
            logger.warning(f"Failed to persist session, fallback to pending: {e}")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """取得 session，先查 pending 暫存再查 MongoDB"""
        if session_id in self._pending:
            return self._pending[session_id]

        try:
            doc = self.sessions_collection.find_one({"session_id": session_id})
            if doc is None:
                logger.warning(f"Session not found in MongoDB: {session_id}")
                return None
            return self._doc_to_session(doc)
        except Exception as e:
            logger.error(f"Failed to get session from MongoDB: {e}")
            return None

    def update_session(self, session: Session) -> Session:
        """Update session in MongoDB."""
        try:
            session.update_timestamp()
            doc = {**session.model_dump(mode="json"), "updated_at": datetime.now()}
            self.sessions_collection.update_one({"session_id": session.session_id}, {"$set": doc}, upsert=True)
            self._pending.pop(session.session_id, None)
            logger.info(f"Updated session: {session.session_id}, step={session.step.value}")
            return session
        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            raise

    def delete_session(self, session_id: str) -> bool:
        """刪除 session"""
        self._pending.pop(session_id, None)
        try:
            result = self.sessions_collection.delete_one({"session_id": session_id})

            if result.deleted_count > 0:
                logger.info(f"Deleted session from MongoDB: {session_id}")
                return True
            else:
                logger.warning(f"Session not found for deletion: {session_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete session from MongoDB: {e}")
            return False

    def rebuild_session_from_logs(self, session_id: str, logs: List[Dict]) -> Optional[Session]:
        """從 conversation logs 重建過期的 JTI session."""
        if not logs:
            return None

        try:
            existing_selected_questions = None
            existing_language = "zh"
            try:
                existing_doc = self.sessions_collection.find_one({"session_id": session_id})
                if existing_doc:
                    existing_selected_questions = existing_doc.get("selected_questions")
                    existing_language = existing_doc.get("language", "zh")
            except Exception:
                pass

            state = _extract_quiz_state_from_logs(logs)
            language = _resolve_session_language(logs, existing_language)
            selected_questions = _reconcile_selected_questions(
                state["selected_questions"],
                snapshot=state["snapshot"],
                existing_selected_questions=existing_selected_questions,
                language=language,
            )
            step = state["step"]
            answers = state["answers"]
            current_q_index = len(answers)
            step, current_question = _resolve_rebuilt_current_question(
                session_id,
                step,
                selected_questions,
                current_q_index,
            )

            session = Session(
                session_id=session_id,
                step=step,
                language=language,
                current_q_index=current_q_index,
                answers=answers,
                selected_questions=selected_questions if selected_questions else None,
                quiz_result_id=state["quiz_result_id"],
                quiz_scores=state["quiz_scores"],
                quiz_result=state["quiz_result"],
                chat_history=state["chat_history"],
                current_question=current_question,
                metadata={},
            )
            _persist_rebuilt_session(self.sessions_collection, session_id, session)
            logger.info(
                f"Rebuilt session from {len(logs)} logs: {session_id[:8]}... "
                f"(step={step}, answers={len(answers)}, questions={len(selected_questions)})"
            )
            return session

        except Exception as e:
            logger.error(f"Failed to rebuild session from logs: {e}", exc_info=True)
            return None

    # === 輔助方法 ===

    @staticmethod
    def _doc_to_session(doc: Dict[str, Any]) -> Optional[Session]:
        """Convert MongoDB doc to Session object."""
        if not doc:
            return None

        cleaned = dict(doc)
        for key in ("_id", "expires_at", "created_at", "updated_at"):
            cleaned.pop(key, None)

        try:
            return Session(**cleaned)
        except Exception as e:
            logger.warning(f"Failed to parse session: {e}")
            return None

    def _find_sessions(self, query: dict) -> List[Session]:
        """通用查詢 helper"""
        try:
            docs = self.sessions_collection.find(query)
            return [s for doc in docs if (s := self._doc_to_session(doc))]
        except Exception as e:
            logger.error(f"Failed to find sessions: {e}")
            return []

    def get_all_sessions(self) -> List[Session]:
        """取得所有 sessions（測試用）"""
        return self._find_sessions({})

    # === 查詢和分析方法 ===

    def get_sessions_by_language(self, language: str) -> List[Session]:
        """按語言查詢 sessions"""
        return self._find_sessions({"language": language})

    def get_sessions_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Session]:
        """按時間範圍查詢 sessions"""
        return self._find_sessions({
            "created_at": {
                "$gte": start_date,
                "$lte": end_date
            }
        })

    def get_statistics(self) -> Dict[str, Any]:
        """取得 session 統計資訊"""
        try:
            total_sessions = self.sessions_collection.count_documents({})

            # 按狀態分組統計
            step_stats = list(
                self.sessions_collection.aggregate([
                    {"$group": {"_id": "$step", "count": {"$sum": 1}}}
                ])
            )

            # 已完成的測驗
            completed_quizzes = self.sessions_collection.count_documents({
                "step": SessionStep.DONE.value
            })

            return {
                "total_sessions": total_sessions,
                "step_distribution": {s["_id"]: s["count"] for s in step_stats},
                "completed_quizzes": completed_quizzes
            }

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
