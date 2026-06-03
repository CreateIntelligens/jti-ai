"""
對話日誌記錄器

職責：
1. 記錄每次對話的詳細資訊
2. 包含時間戳、session_id、使用者訊息、Agent 回應、工具呼叫
3. 方便 debug 和分析
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_TZ_TAIPEI = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


class ConversationLogger:
    """對話日誌記錄器 (檔案/記憶體備份版本)"""

    def __init__(self, log_dir: str = "logs/conversations"):
        """初始化日誌記錄器

        Args:
            log_dir: 日誌檔案目錄
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ConversationLogger initialized: {self.log_dir}")

    def _get_log_paths(self, session_id: str, timestamp: Optional[datetime] = None) -> tuple[Path, Path]:
        """Find or create log paths (jsonl and txt) for a session."""
        log_file = next(self.log_dir.glob(f"*{session_id}.jsonl"), None)
        if log_file is None:
            ts = timestamp or datetime.now(_TZ_TAIPEI)
            prefix = ts.strftime("%Y%m%d_%H%M%S")
            log_file = self.log_dir / f"{prefix}_{session_id}.jsonl"
        return log_file, log_file.with_suffix(".txt")

    def log_conversation(
        self,
        session_id: str,
        user_message: str,
        agent_response: str,
        mode: str,
        tool_calls: Optional[List[Dict]] = None,
        session_state: Optional[Dict] = None,
        error: Optional[str] = None,
        responded_at: Optional[datetime] = None,
        citations: Optional[List[Dict]] = None,
        image_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        **kwargs,
    ) -> Optional[tuple[str, int]]:
        """記錄一次對話"""
        if not mode:
            raise ValueError("mode is required")

        try:
            timestamp = datetime.now(_TZ_TAIPEI)

            # 讀取已存在的對話以決定下一輪 turn_number
            logs = self.get_session_logs(session_id)
            if turn_number is None:
                max_turn = max((log.get("turn_number", 0) for log in logs), default=0)
                turn_number = max_turn + 1

            log_entry = {
                "timestamp": timestamp.isoformat(),
                "responded_at": (responded_at or timestamp).isoformat(),
                "session_id": session_id,
                "mode": mode,
                "turn_number": turn_number,
                "user_message": user_message,
                "agent_response": agent_response,
                "tool_calls": tool_calls or [],
                "session_state": session_state or {},
                "citations": citations or [],
                "image_id": image_id or None,
                "error": error
            }

            log_file, readable_log_file = self._get_log_paths(session_id, timestamp)

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            with open(readable_log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] (Turn #{turn_number})\n")
                f.write(f"Session: {session_id}\n")
                f.write(f"\n👤 使用者:\n{user_message}\n")

                if tool_calls:
                    f.write("\n🔧 工具呼叫:\n")
                    for tool_call in tool_calls:
                        f.write(f"  - {tool_call.get('tool')}({tool_call.get('args', {})})\n")
                        result = json.dumps(tool_call.get("result", {}), ensure_ascii=False)
                        f.write(f"    結果: {result}\n")

                f.write(f"\n🤖 Agent:\n{agent_response}\n")

                if session_state:
                    f.write("\n📊 Session 狀態:\n")
                    f.write(f"  - 階段: {session_state.get('step')}\n")
                    f.write(f"  - 已回答: {session_state.get('answers_count', 0)}/4\n")
                    if rid := session_state.get("quiz_result_id"):
                        f.write(f"  - 測驗結果: {rid}\n")

                if error:
                    f.write(f"\n❌ 錯誤:\n{error}\n")
                f.write(f"{'='*80}\n")

            return (str(turn_number), turn_number)

        except Exception as e:
            logger.error(f"Failed to log conversation: {e}", exc_info=True)
            return None

    def get_session_logs(self, session_id: str) -> List[Dict]:
        """取得特定 session 的所有日誌"""
        log_file, _ = self._get_log_paths(session_id)
        if not log_file.exists():
            return []

        logs = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to read session logs: {e}")
        return sorted(logs, key=lambda x: x.get("turn_number", 0))

    def get_session_logs_by_mode(self, mode: str) -> List[Dict]:
        """按模式查詢所有對話紀錄"""
        logs = []
        try:
            for log_file in self.log_dir.glob("*.jsonl"):
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            doc = json.loads(line)
                            if doc.get("mode") == mode:
                                logs.append(doc)
        except Exception as e:
            logger.error(f"Failed to get session logs by mode: {e}")
        return sorted(logs, key=lambda x: x.get("timestamp", ""), reverse=True)

    def delete_session_logs(self, session_id: str) -> int:
        """刪除特定 session 的所有對話紀錄"""
        log_file, readable_log_file = self._get_log_paths(session_id)
        if not log_file.exists():
            return 0

        count = 0
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
            log_file.unlink()
            if readable_log_file.exists():
                readable_log_file.unlink()
            logger.info(f"Deleted {count} conversation logs for session {session_id[:8]}...")
        except Exception as e:
            logger.error(f"Failed to delete session logs: {e}")
            return 0
        return count

    def delete_turns_from(self, session_id: str, from_turn_number: int) -> int:
        """刪除指定 session 中 turn_number >= from_turn_number 的紀錄"""
        log_file, readable_log_file = self._get_log_paths(session_id)
        if not log_file.exists():
            return 0

        try:
            logs = self.get_session_logs(session_id)
            keep_logs = [l for l in logs if l.get("turn_number", 0) < from_turn_number]
            deleted_count = len(logs) - len(keep_logs)

            if deleted_count > 0:
                if not keep_logs:
                    log_file.unlink()
                    if readable_log_file.exists():
                        readable_log_file.unlink()
                else:
                    with open(log_file, "w", encoding="utf-8") as f:
                        for entry in keep_logs:
                            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                logger.info(f"Deleted {deleted_count} turns (>= #{from_turn_number}) for session {session_id[:8]}...")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete turns from session {session_id}: {e}")
            return 0

    def list_sessions(self) -> List[str]:
        """列出所有有日誌的 session"""
        return sorted(f.name.split("_")[-1].replace(".jsonl", "") for f in self.log_dir.glob("*.jsonl"))

    def _matches_query(self, doc: dict, query: dict) -> bool:
        """Helper to match a document against a query dictionary (similar to MongoDB query filter)."""
        for k, v in query.items():
            if k == "session_id":
                if isinstance(v, dict) and "$in" in v:
                    if doc.get("session_id") not in v["$in"]:
                        return False
                elif doc.get("session_id") != v:
                    return False
            elif k == "mode":
                if doc.get("mode") != v:
                    return False
            elif k == "store_name":
                if doc.get("store_name") != v:
                    return False
            elif k == "timestamp":
                doc_ts_str = doc.get("timestamp")
                if not doc_ts_str:
                    return False
                doc_ts = datetime.fromisoformat(doc_ts_str)
                if isinstance(v, dict):
                    if "$gte" in v:
                        gte_val = v["$gte"]
                        if isinstance(gte_val, str):
                            gte_val = datetime.fromisoformat(gte_val)
                        if doc_ts < gte_val:
                            return False
                    if "$lte" in v:
                        lte_val = v["$lte"]
                        if isinstance(lte_val, str):
                            lte_val = datetime.fromisoformat(lte_val)
                        if doc_ts > lte_val:
                            return False
        return True

    def get_paginated_session_ids(
        self,
        query: Dict[str, Any],
        page: int = 1,
        page_size: int = 10
    ) -> tuple[List[str], int]:
        """分頁取得符合條件的 session_ids"""
        try:
            # 遍歷所有紀錄
            all_logs = []
            for log_file in self.log_dir.glob("*.jsonl"):
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            doc = json.loads(line)
                            if self._matches_query(doc, query):
                                all_logs.append(doc)

            # 按 session_id 分組，並取得最新時間
            session_actives = {}
            for doc in all_logs:
                sid = doc.get("session_id")
                ts_str = doc.get("timestamp", "")
                if sid:
                    if sid not in session_actives or ts_str > session_actives[sid]:
                        session_actives[sid] = ts_str

            # 按最新活動時間排序
            sorted_sessions = sorted(session_actives.keys(), key=lambda s: session_actives[s], reverse=True)
            total_sessions = len(sorted_sessions)

            # 分頁
            start_idx = (page - 1) * page_size
            paginated = sorted_sessions[start_idx : start_idx + page_size]

            return paginated, total_sessions

        except Exception as e:
            logger.error(f"Failed to get paginated session ids: {e}")
            return [], 0

    def get_logs_for_sessions(self, session_ids: List[str]) -> List[Dict]:
        """取得指定 session_ids 的所有對話紀錄"""
        if not session_ids:
            return []

        logs = []
        try:
            sid_set = set(session_ids)
            for log_file in self.log_dir.glob("*.jsonl"):
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            doc = json.loads(line)
                            if doc.get("session_id") in sid_set:
                                logs.append(doc)
        except Exception as e:
            logger.error(f"Failed to get logs for sessions: {e}")
        return sorted(logs, key=lambda x: (x.get("session_id", ""), x.get("turn_number", 0)))
