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
from typing import Dict, List, Optional

_TZ_TAIPEI = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


class ConversationLogger:
    """對話日誌記錄器"""

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
        **kwargs,
    ) -> None:
        """記錄一次對話"""
        if not mode:
            raise ValueError("mode is required")

        try:
            timestamp = datetime.now(_TZ_TAIPEI)
            log_entry = {
                "timestamp": timestamp.isoformat(),
                "responded_at": (responded_at or timestamp).isoformat(),
                "session_id": session_id,
                "mode": mode,
                "user_message": user_message,
                "agent_response": agent_response,
                "tool_calls": tool_calls or [],
                "session_state": session_state or {},
                "error": error
            }

            log_file, readable_log_file = self._get_log_paths(session_id, timestamp)

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            with open(readable_log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}]\n")
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

        except Exception as e:
            logger.error(f"Failed to log conversation: {e}", exc_info=True)

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
        return logs

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

    def list_sessions(self) -> List[str]:
        """列出所有有日誌的 session"""
        return sorted(f.stem for f in self.log_dir.glob("*.jsonl"))
