"""
MongoDB Session 管理服務

職責：
1. 在 MongoDB 中進行 Session CRUD
2. 狀態機管理
3. 支持查詢和分析
"""

from typing import Dict, Optional, List, Any
from datetime import datetime

from app.models.session import Session, SessionStep, GameMode
from app.services.mongo_client import get_mongo_db
from .session_state_mixin import SessionStateMixin
import logging

logger = logging.getLogger(__name__)


class MongoSessionManager(SessionStateMixin):
    """MongoDB Session 管理器"""

    def __init__(self):
        self.db = get_mongo_db()
        self.sessions_collection = self.db["sessions"]

    def create_session(
        self,
        mode: GameMode = GameMode.COLOR,
        language: str = "zh"
    ) -> Session:
        """建立新 session"""
        session = Session(mode=mode, language=language)

        # 轉換為可序列化的字典
        session_dict = session.model_dump(mode="json")

        # 添加 MongoDB 相關字段
        session_dict["created_at"] = datetime.now()
        session_dict["updated_at"] = datetime.now()

        try:
            result = self.sessions_collection.insert_one(session_dict)
            logger.info(
                f"Created session in MongoDB: {session.session_id} "
                f"(mode={mode.value}, language={language})"
            )
            return session
        except Exception as e:
            logger.error(f"Failed to create session in MongoDB: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Session]:
        """取得 session"""
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
        """更新 session"""
        try:
            session.update_timestamp()
            session_dict = session.model_dump(mode="json")

            session_dict["updated_at"] = datetime.now()

            result = self.sessions_collection.update_one(
                {"session_id": session.session_id},
                {"$set": session_dict}
            )

            if result.matched_count == 0:
                logger.warning(f"Session not found for update: {session.session_id}")
                return session

            logger.info(
                f"Updated session in MongoDB: {session.session_id}, "
                f"step={session.step.value}, answers={len(session.answers)}"
            )
            return session

        except Exception as e:
            logger.error(f"Failed to update session in MongoDB: {e}")
            raise

    def delete_session(self, session_id: str) -> bool:
        """刪除 session"""
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
        """從 conversation logs 重建過期的 JTI session

        Args:
            session_id: 原始 session ID
            logs: 該 session 的 conversation logs（已按 turn_number 排序）

        Returns:
            重建的 Session 物件（已寫入 MongoDB），或 None（logs 為空）
        """
        if not logs:
            return None

        try:
            # === 從 logs 提取資料 ===
            answers = {}            # {question_id: option_id}
            selected_questions = [] # 按順序收集的題目
            color_scores = {}
            color_result = None
            color_result_id = None
            chat_history = []

            for log in logs:
                # 收集 chat_history
                user_msg = log.get("user_message", "")
                agent_resp = log.get("agent_response", "")
                if user_msg:
                    chat_history.append({"role": "user", "content": user_msg})
                if agent_resp:
                    chat_history.append({"role": "assistant", "content": agent_resp})

                # 解析 tool_calls
                for tc in log.get("tool_calls", []):
                    tool = tc.get("tool") or tc.get("tool_name")
                    result = tc.get("result", {})

                    if tool == "start_quiz" and result.get("current_question"):
                        # 第一題
                        selected_questions.append(result["current_question"])

                    elif tool == "submit_answer":
                        if result.get("success"):
                            question_id = result.get("answered")
                            option_id = result.get("selected")
                            if question_id and option_id:
                                answers[question_id] = option_id

                        if result.get("next_question"):
                            # 後續題目
                            selected_questions.append(result["next_question"])

                        # 提取 color_result（最後一題完成時）
                        if result.get("color_result"):
                            cr = result["color_result"]
                            color_scores = cr.get("color_scores", {})
                            color_result = cr.get("result")

            # === 從最後一筆 log 的 session_snapshot 取得狀態 ===
            last_log = logs[-1]
            snapshot = last_log.get("session_snapshot") or last_log.get("session_state") or {}
            step = snapshot.get("step", "WELCOME")
            color_result_id = snapshot.get("color_result_id") or color_result_id

            # === 推斷語言（預設 zh） ===
            language = "zh"

            # === 計算 current_q_index 和 current_question ===
            current_q_index = len(answers)
            current_question = None

            if step == "QUIZ" and selected_questions:
                if current_q_index < len(selected_questions):
                    current_question = selected_questions[current_q_index]
                else:
                    # selected_questions 不完整，降級為 WELCOME
                    logger.warning(
                        f"Rebuilding session {session_id[:8]}...: "
                        f"selected_questions ({len(selected_questions)}) < current_q_index ({current_q_index}), "
                        f"degrading to WELCOME"
                    )
                    step = "WELCOME"
            elif step == "QUIZ" and not selected_questions:
                # 沒有 selected_questions 資料，降級為 WELCOME
                logger.warning(
                    f"Rebuilding session {session_id[:8]}...: no selected_questions, degrading to WELCOME"
                )
                step = "WELCOME"

            metadata = {}

            # === 建立 Session 物件 ===
            session = Session(
                session_id=session_id,
                mode=GameMode.COLOR,
                step=step,
                language=language,
                quiz_id="color_taste",
                current_q_index=current_q_index,
                answers=answers,
                selected_questions=selected_questions if selected_questions else None,
                color_result_id=color_result_id,
                color_scores=color_scores,
                color_result=color_result,
                chat_history=chat_history,
                current_question=current_question,
                metadata=metadata,
            )

            # === 寫入 MongoDB ===
            session_dict = session.model_dump(mode="json")
            session_dict["created_at"] = datetime.now()
            session_dict["updated_at"] = datetime.now()

            self.sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": session_dict},
                upsert=True
            )
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
        cleaned = dict(doc)
        cleaned.pop("_id", None)
        cleaned.pop("expires_at", None)
        cleaned.pop("created_at", None)
        cleaned.pop("updated_at", None)
        try:
            return Session(**cleaned)
        except Exception as e:
            logger.warning(f"Failed to parse session document: {e}")
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

    def get_sessions_by_mode(self, mode: GameMode) -> List[Session]:
        """按模式查詢 sessions"""
        return self._find_sessions({"mode": mode.value})

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

            # 按模式分組統計
            mode_stats = list(
                self.sessions_collection.aggregate([
                    {"$group": {"_id": "$mode", "count": {"$sum": 1}}}
                ])
            )

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
                "mode_distribution": {s["_id"]: s["count"] for s in mode_stats},
                "step_distribution": {s["_id"]: s["count"] for s in step_stats},
                "completed_quizzes": completed_quizzes
            }

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
