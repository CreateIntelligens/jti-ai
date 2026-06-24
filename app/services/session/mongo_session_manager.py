"""
MongoDB Session 管理服務

職責：
1. 在 MongoDB 中進行 Session CRUD
2. 狀態機管理
3. 支持查詢和分析
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.session import Session, SessionStep, compute_expires_at
from app.services.mongo_client import get_mongo_db
from app.tools.jti.quiz import complete_selected_questions, get_total_questions

from .session_state_mixin import SessionStateMixin

logger = logging.getLogger(__name__)


_SESSION_CACHE_KEY_PREFIX = "session"
_DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_CLIENT_AUTO = object()


def _build_cache_client():
    """Create a Redis client when REDIS_URL is configured.

    Redis is a performance cache only. If the package, URL, or server is not
    available, session persistence continues through MongoDB.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis
    except Exception as exc:
        logger.warning("Redis cache disabled: redis package unavailable (%s)", exc)
        return None

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        logger.info("Redis session cache enabled")
        return client
    except Exception as exc:
        logger.warning("Redis session cache disabled: %s", exc)
        return None


def _cache_ttl_seconds(expires_at: Any, *, now: Optional[datetime] = None) -> int:
    if not isinstance(expires_at, datetime):
        return _DEFAULT_CACHE_TTL_SECONDS

    if now is not None:
        current = now
    elif expires_at.tzinfo is not None:
        current = datetime.now(expires_at.tzinfo)
    else:
        current = datetime.now()
    ttl = int((expires_at - current).total_seconds())
    return max(1, ttl)


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
    now = datetime.now()
    session_dict = _session_doc_with_expiry(session, now)
    session_dict["created_at"] = now
    sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": session_dict},
        upsert=True,
    )


def _session_doc_with_expiry(session: Session, now: datetime) -> Dict[str, Any]:
    """Build a MongoDB session document with dynamic TTL metadata."""
    session_dict = session.model_dump(mode="json")
    session_dict["updated_at"] = now
    # Persistence-only metadata; keep Session.model_dump() payload shape unchanged.
    session_dict["expires_at"] = compute_expires_at(session.step, now)
    return session_dict


class MongoSessionManager(SessionStateMixin):
    """MongoDB Session 管理器"""

    def __init__(self, db_name: str, cache_client: Any = _CACHE_CLIENT_AUTO):
        self.db_name = db_name
        self.db = get_mongo_db(db_name)
        self.sessions_collection = self.db["sessions"]
        self.cache = (
            _build_cache_client()
            if cache_client is _CACHE_CLIENT_AUTO
            else cache_client
        )

    def _cache_key(self, session_id: str) -> str:
        return f"{_SESSION_CACHE_KEY_PREFIX}:{self.db_name}:{session_id}"

    def _cache_get(self, session_id: str) -> Optional[Session]:
        if self.cache is None:
            return None

        try:
            key = self._cache_key(session_id)
            cached = self.cache.get(key)
            if not cached:
                return None
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            payload = json.loads(cached)
            return Session(**payload)
        except Exception as exc:
            logger.warning("Ignoring invalid Redis session cache for %s: %s", session_id, exc)
            try:
                self.cache.delete(key)
            except Exception:
                pass
            return None

    def _cache_set(self, session: Session, expires_at: Any = None) -> None:
        if self.cache is None:
            return

        try:
            expiry = (
                expires_at
                if expires_at is not None
                else compute_expires_at(session.step, datetime.now())
            )
            ttl = _cache_ttl_seconds(expiry)
            payload = json.dumps(session.model_dump(mode="json"), ensure_ascii=False)
            self.cache.set(self._cache_key(session.session_id), payload, ex=ttl)
        except Exception as exc:
            logger.warning(
                "Failed to write Redis session cache for %s: %s",
                session.session_id,
                exc,
            )

    def _cache_delete(self, session_id: str) -> None:
        if self.cache is None:
            return
        try:
            self.cache.delete(self._cache_key(session_id))
        except Exception as exc:
            logger.warning("Failed to delete Redis session cache for %s: %s", session_id, exc)

    def create_session(self, language: str = "zh") -> Session:
        """Create new session（建立即落庫，多 worker 共享狀態）.

        早期版本用 process 內 `_pending` 暫存做 lazy-write 以避免空 session 積壓，
        但記憶體不跨 worker：prod 多 worker 下 /chat/start 與 /chat/message 打到
        不同 worker 會讀不到 session（404 失憶）。改為建立即寫 MongoDB，所有 worker
        經 DB 共享狀態；空 session 的積壓改由動態 TTL（compute_expires_at）短時回收。
        """
        session = Session(language=language)
        self._upsert_session(session)
        logger.info(f"Created session (persisted): {session.session_id}")
        return session

    def _upsert_session(self, session: Session) -> None:
        """以動態 expires_at 落庫 session（create / update 共用）。"""
        doc = _session_doc_with_expiry(session, datetime.now())
        self.sessions_collection.update_one(
            {"session_id": session.session_id}, {"$set": doc}, upsert=True
        )
        self._cache_set(session, doc.get("expires_at"))

    def get_session(self, session_id: str) -> Optional[Session]:
        """取得 session（Redis read-through，miss 時回 MongoDB）"""
        try:
            cached = self._cache_get(session_id)
            if cached is not None:
                return cached

            doc = self.sessions_collection.find_one({"session_id": session_id})
            if doc is None:
                logger.warning(f"Session not found in MongoDB: {session_id}")
                return None
            session = self._doc_to_session(doc)
            if session is not None:
                self._cache_set(session, doc.get("expires_at"))
            return session
        except Exception as e:
            logger.error(f"Failed to get session from MongoDB: {e}")
            return None

    def update_session(self, session: Session) -> Session:
        """Update session in MongoDB.

        每次寫入都依 step 重算動態 expires_at，配合 sessions 集合的
        TTL 索引（expireAfterSeconds=0）讓過期文件被自動回收。
        """
        try:
            session.update_timestamp()
            self._upsert_session(session)
            logger.info(f"Updated session: {session.session_id}, step={session.step.value}")
            return session
        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            raise

    def delete_session(self, session_id: str) -> bool:
        """刪除 session"""
        try:
            result = self.sessions_collection.delete_one({"session_id": session_id})
            self._cache_delete(session_id)

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
            self._cache_set(session)
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
