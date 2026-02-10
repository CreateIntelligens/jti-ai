"""
MongoDB Session 管理服務

職責：
1. 在 MongoDB 中進行 Session CRUD
2. 狀態機管理
3. 自動過期清理
4. 支持查詢和分析
"""

from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta

from app.models.session import Session, SessionStep, GameMode
from app.services.mongo_client import get_mongo_db
from app.services.session_state_mixin import SessionStateMixin
import logging

logger = logging.getLogger(__name__)


class MongoSessionManager(SessionStateMixin):
    """MongoDB Session 管理器"""

    def __init__(self, idle_timeout_minutes: int = 30):
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
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
        session_dict["expires_at"] = datetime.now() + self.idle_timeout
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

            # 檢查是否已過期
            expires_at = doc.get("expires_at")
            if isinstance(expires_at, datetime) and datetime.now() > expires_at:
                logger.info(f"Session expired, deleting: {session_id}")
                self.delete_session(session_id)
                return None

            # 移除 MongoDB 內部字段，重新構建 Session 物件
            doc.pop("_id", None)
            doc.pop("expires_at", None)
            doc.pop("created_at", None)
            doc.pop("updated_at", None)

            session = Session(**doc)
            return session

        except Exception as e:
            logger.error(f"Failed to get session from MongoDB: {e}")
            return None

    def update_session(self, session: Session) -> Session:
        """更新 session"""
        try:
            session.update_timestamp()
            session_dict = session.model_dump(mode="json")

            # 更新 updated_at 和 expires_at
            now = datetime.now()
            session_dict["updated_at"] = now
            session_dict["expires_at"] = now + self.idle_timeout

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

    def get_all_sessions(self) -> List[Session]:
        """取得所有 sessions（測試用）"""
        try:
            docs = self.sessions_collection.find()
            sessions = []

            for doc in docs:
                session = self._doc_to_session(doc)
                if session:
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get all sessions from MongoDB: {e}")
            return []

    def clear_expired_sessions(self) -> int:
        """清理過期 sessions"""
        try:
            now = datetime.now()
            result = self.sessions_collection.delete_many(
                {"expires_at": {"$lt": now}}
            )

            deleted_count = result.deleted_count
            logger.info(f"Cleared {deleted_count} expired sessions from MongoDB")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to clear expired sessions from MongoDB: {e}")
            return 0

    # === 查詢和分析方法 ===

    def get_sessions_by_mode(self, mode: GameMode) -> List[Session]:
        """按模式查詢 sessions"""
        try:
            docs = self.sessions_collection.find({"mode": mode.value})
            sessions = []

            for doc in docs:
                session = self._doc_to_session(doc)
                if session:
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions by mode: {e}")
            return []

    def get_sessions_by_language(self, language: str) -> List[Session]:
        """按語言查詢 sessions"""
        try:
            docs = self.sessions_collection.find({"language": language})
            sessions = []

            for doc in docs:
                session = self._doc_to_session(doc)
                if session:
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions by language: {e}")
            return []

    def get_sessions_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Session]:
        """按時間範圍查詢 sessions"""
        try:
            docs = self.sessions_collection.find({
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            })
            sessions = []

            for doc in docs:
                session = self._doc_to_session(doc)
                if session:
                    sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions by date range: {e}")
            return []

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
