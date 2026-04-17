"""
一般知識庫 Chat Session 管理服務

職責：
1. 在 MongoDB 中管理一般知識庫的 Chat Session
2. 支持多輪對話歷史持久化
"""

from typing import Dict, Optional, List, Any
from datetime import datetime
import logging

from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)


class GeneralChatSessionManager:
    """一般知識庫 Chat Session 管理器"""

    def __init__(self):
        self.db = get_mongo_db("jti_app")
        self.collection = self.db["general_chat_sessions"]

        # 建立索引
        self.collection.create_index("session_id", unique=True)

    @staticmethod
    def _strip_internal_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Remove MongoDB internal fields from a session document."""
        doc.pop("_id", None)
        return doc

    def create_session(self, session_id: str, store_name: str, model: str, system_instruction: Optional[str] = None) -> Dict[str, Any]:
        """Create or update session."""
        now = datetime.now()
        doc = {
            "session_id": session_id,
            "store_name": store_name,
            "model": model,
            "system_instruction": system_instruction,
            "chat_history": [],
            "created_at": now,
            "updated_at": now,
        }
        self.collection.update_one({"session_id": session_id}, {"$set": doc}, upsert=True)
        return doc

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session without internal ID."""
        doc = self.collection.find_one({"session_id": session_id})
        if doc is None:
            return None
        return self._strip_internal_id(doc)

    def add_message(self, session_id: str, role: str, content: str, citations: Optional[List[Dict]] = None) -> bool:
        """新增訊息到對話歷史"""
        try:
            entry: Dict[str, Any] = {"role": role, "content": content}
            if citations:
                entry["citations"] = citations
            result = self.collection.update_one(
                {"session_id": session_id},
                {
                    "$push": {"chat_history": entry},
                    "$set": {"updated_at": datetime.now()},
                },
            )

            if result.matched_count == 0:
                logger.warning(f"Session not found for add_message: {session_id}")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to add message to session {session_id}: {e}")
            return False

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """取得對話歷史"""
        try:
            doc = self.collection.find_one(
                {"session_id": session_id},
                {"chat_history": 1},
            )
            if doc is None:
                return []

            return doc.get("chat_history", [])
        except Exception as e:
            logger.error(f"Failed to get history for session {session_id}: {e}")
            return []

    def truncate_history(self, session_id: str, keep_turns: int) -> bool:
        """截斷對話歷史，只保留前 keep_turns 輪（每輪 = user + model = 2 條）

        Args:
            session_id: Session ID
            keep_turns: 保留幾輪對話

        Returns:
            是否成功
        """
        try:
            keep_count = keep_turns * 2
            doc = self.collection.find_one(
                {"session_id": session_id},
                {"chat_history": 1},
            )
            if doc is None:
                logger.warning(f"Session not found for truncate: {session_id}")
                return False

            current_history = doc.get("chat_history", [])
            truncated = current_history[:keep_count]

            self.collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "chat_history": truncated,
                        "updated_at": datetime.now(),
                    }
                },
            )
            logger.info(
                f"Truncated session {session_id[:8]}... "
                f"from {len(current_history)} to {len(truncated)} messages "
                f"(keep_turns={keep_turns})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to truncate session {session_id}: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """刪除 session"""
        try:
            result = self.collection.delete_one({"session_id": session_id})
            if result.deleted_count > 0:
                logger.info(f"Deleted general chat session: {session_id}")
                return True
            logger.warning(f"Session not found for deletion: {session_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete general chat session: {e}")
            return False

    def list_sessions(self, store_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出 sessions，可選擇按 store 篩選"""
        try:
            query = {}
            if store_name is not None:
                query["store_name"] = store_name

            return [self._strip_internal_id(doc) for doc in self.collection.find(query)]
        except Exception as e:
            logger.error(f"Failed to list general chat sessions: {e}")
            return []
