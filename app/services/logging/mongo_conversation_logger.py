"""
MongoDB 對話日誌記錄器

職責：
1. 在 MongoDB 中記錄每次對話
2. 支持完整的查詢和分析
3. 保留檔案日誌備份（可選）
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from app.services.mongo_client import get_mongo_db

logger = logging.getLogger(__name__)


class MongoConversationLogger:
    """MongoDB 對話日誌記錄器"""

    def __init__(self, keep_file_logs: bool = True):
        """初始化日誌記錄器

        Args:
            keep_file_logs: 是否同時保留檔案日誌備份
        """
        self.db = get_mongo_db()
        self.conversations_collection = self.db["conversations"]
        self.keep_file_logs = keep_file_logs
        logger.info("MongoConversationLogger initialized")

    def log_conversation(
        self,
        session_id: str,
        user_message: str,
        agent_response: str,
        tool_calls: Optional[List[Dict]] = None,
        session_state: Optional[Dict] = None,
        error: Optional[str] = None,
        mode: str = "jti"
    ) -> Optional[str]:
        """記錄一次對話

        Args:
            session_id: Session ID
            user_message: 使用者訊息
            agent_response: Agent 回應
            tool_calls: 工具呼叫記錄
            session_state: Session 狀態快照
            error: 錯誤訊息（如果有）
            mode: 模式 ("jti" 或 "general")

        Returns:
            記錄的 MongoDB document ID，若失敗返回 None
        """
        try:
            # 獲取該 session 現有的對話輪次
            last_turn = self.conversations_collection.find_one(
                {"session_id": session_id},
                sort=[("turn_number", -1)]
            )
            turn_number = (last_turn["turn_number"] + 1) if last_turn else 1

            # 構建日誌記錄
            log_entry = {
                "session_id": session_id,
                "mode": mode,
                "turn_number": turn_number,
                "timestamp": datetime.now(),
                "user_message": user_message,
                "agent_response": agent_response,
                "tool_calls": tool_calls or [],
                "session_snapshot": session_state or {},
                "error": error
            }

            result = self.conversations_collection.insert_one(log_entry)

            logger.debug(
                f"Logged conversation to MongoDB: "
                f"session={session_id[:8]}..., turn={turn_number}"
            )

            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Failed to log conversation to MongoDB: {e}")
            return None

    def get_session_logs(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """取得特定 session 的所有日誌

        Args:
            session_id: Session ID
            limit: 最多返回筆數（None = 全部）

        Returns:
            日誌記錄列表
        """
        try:
            query = {"session_id": session_id}

            if limit:
                docs = list(
                    self.conversations_collection.find(query)
                    .sort("turn_number", 1)
                    .limit(limit)
                )
            else:
                docs = list(
                    self.conversations_collection.find(query)
                    .sort("turn_number", 1)
                )

            # 轉換 ObjectId 為字符串，datetime 為 ISO format
            for doc in docs:
                doc["_id"] = str(doc["_id"])
                if isinstance(doc["timestamp"], datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()

            return docs

        except Exception as e:
            logger.error(f"Failed to get session logs from MongoDB: {e}")
            return []

    def get_session_logs_by_mode(self, mode: str) -> List[Dict]:
        """按模式查詢所有對話紀錄

        Args:
            mode: "jti" 或 "general"

        Returns:
            符合的日誌記錄列表
        """
        try:
            docs = list(
                self.conversations_collection.find({"mode": mode})
                .sort("timestamp", -1)
            )

            for doc in docs:
                doc["_id"] = str(doc["_id"])
                if isinstance(doc["timestamp"], datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()

            return docs

        except Exception as e:
            logger.error(f"Failed to get logs by mode: {e}")
            return []

    def list_sessions(self) -> List[str]:
        """列出所有有對話紀錄的 session

        Returns:
            Session ID 列表（按最近使用排序）
        """
        try:
            results = self.conversations_collection.aggregate([
                {"$group": {"_id": "$session_id", "last_turn": {"$max": "$turn_number"}}},
                {"$sort": {"_id": -1}}
            ])

            sessions = [r["_id"] for r in results]
            return sessions

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """取得對話記錄統計資訊

        Returns:
            統計數據
        """
        try:
            total_conversations = self.conversations_collection.count_documents({})

            # 按模式分組統計
            mode_stats = list(
                self.conversations_collection.aggregate([
                    {"$group": {"_id": "$mode", "count": {"$sum": 1}}}
                ])
            )

            # 平均對話輪次（per session）
            avg_turns = list(
                self.conversations_collection.aggregate([
                    {"$group": {"_id": "$session_id", "turns": {"$max": "$turn_number"}}},
                    {"$group": {"_id": None, "avg": {"$avg": "$turns"}}}
                ])
            )

            # 工具使用統計
            tool_stats = list(
                self.conversations_collection.aggregate([
                    {"$unwind": "$tool_calls"},
                    {"$group": {"_id": "$tool_calls.tool_name", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}}
                ])
            )

            return {
                "total_conversations": total_conversations,
                "mode_distribution": {s["_id"]: s["count"] for s in mode_stats},
                "avg_turns_per_session": avg_turns[0]["avg"] if avg_turns else 0,
                "tool_usage": {s["_id"]: s["count"] for s in tool_stats}
            }

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    def get_conversations_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        mode: Optional[str] = None
    ) -> List[Dict]:
        """按時間範圍查詢對話記錄

        Args:
            start_date: 開始日期
            end_date: 結束日期
            mode: 可選篩選模式 ("jti" 或 "general")

        Returns:
            符合的對話記錄
        """
        try:
            query = {
                "timestamp": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }

            if mode:
                query["mode"] = mode

            docs = list(
                self.conversations_collection.find(query)
                .sort("timestamp", -1)
            )

            for doc in docs:
                doc["_id"] = str(doc["_id"])
                if isinstance(doc["timestamp"], datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()

            return docs

        except Exception as e:
            logger.error(f"Failed to get conversations by date range: {e}")
            return []

    def get_tool_call_statistics(self) -> Dict[str, Any]:
        """取得工具呼叫統計

        Returns:
            工具使用詳細統計
        """
        try:
            stats = list(
                self.conversations_collection.aggregate([
                    {"$unwind": "$tool_calls"},
                    {
                        "$group": {
                            "_id": "$tool_calls.tool_name",
                            "count": {"$sum": 1},
                            "avg_execution_time": {
                                "$avg": "$tool_calls.execution_time_ms"
                            }
                        }
                    },
                    {"$sort": {"count": -1}}
                ])
            )

            return {
                tool["_id"]: {
                    "count": tool["count"],
                    "avg_execution_time_ms": tool.get("avg_execution_time", 0)
                }
                for tool in stats
            }

        except Exception as e:
            logger.error(f"Failed to get tool call statistics: {e}")
            return {}

    def delete_session_logs(self, session_id: str) -> int:
        """刪除特定 session 的所有對話紀錄

        Args:
            session_id: Session ID

        Returns:
            刪除的記錄數
        """
        try:
            result = self.conversations_collection.delete_many({
                "session_id": session_id
            })
            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} conversation logs for session {session_id[:8]}...")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete session logs: {e}")
            return 0

    def delete_old_logs(self, days: int = 30) -> int:
        """刪除指定天數前的對話紀錄

        Args:
            days: 保留最近 N 天的記錄

        Returns:
            刪除的記錄數
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            result = self.conversations_collection.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })

            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} old conversation logs")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete old logs: {e}")
            return 0
