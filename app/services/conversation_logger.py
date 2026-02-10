"""
對話日誌記錄器

職責：
1. 記錄每次對話的詳細資訊
2. 包含時間戳、session_id、使用者訊息、Agent 回應、工具呼叫
3. 方便 debug 和分析
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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

    def log_conversation(
        self,
        session_id: str,
        user_message: str,
        agent_response: str,
        tool_calls: Optional[List[Dict]] = None,
        session_state: Optional[Dict] = None,
        error: Optional[str] = None,
        mode: str = "jti"
    ) -> None:
        """記錄一次對話

        Args:
            session_id: Session ID
            user_message: 使用者訊息
            agent_response: Agent 回應
            tool_calls: 工具呼叫記錄
            session_state: Session 狀態
            error: 錯誤訊息（如果有）
            mode: 對話模式 (jti 或 general)
        """
        try:
            timestamp = datetime.now()

            # 構建日誌記錄
            log_entry = {
                "timestamp": timestamp.isoformat(),
                "session_id": session_id,
                "mode": mode,
                "user_message": user_message,
                "agent_response": agent_response,
                "tool_calls": tool_calls or [],
                "session_state": session_state or {},
                "error": error
            }

            # 檔名格式: YYYYMMDD_HHMMSS_{session_id}
            # 如果檔案已存在，就沿用舊檔名；否則用當前時間戳建立新檔
            # 找出是否已有這個 session 的檔案
            existing_files = list(self.log_dir.glob(f"*{session_id}.jsonl"))
            if existing_files:
                # 使用現有檔名
                log_file = existing_files[0]
                readable_log_file = existing_files[0].with_suffix('.txt')
            else:
                # 建立新檔名（加上時間戳）
                timestamp_prefix = timestamp.strftime("%Y%m%d_%H%M%S")
                log_file = self.log_dir / f"{timestamp_prefix}_{session_id}.jsonl"
                readable_log_file = self.log_dir / f"{timestamp_prefix}_{session_id}.txt"

            # 寫入 session 專屬的日誌檔案（JSONL 格式）
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            # 同時寫入可讀的文字日誌
            with open(readable_log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}]\n")
                f.write(f"Session: {session_id}\n")
                f.write(f"\n👤 使用者:\n{user_message}\n")

                if tool_calls:
                    f.write(f"\n🔧 工具呼叫:\n")
                    for tool_call in tool_calls:
                        f.write(f"  - {tool_call.get('tool')}({tool_call.get('args', {})})\n")
                        f.write(f"    結果: {json.dumps(tool_call.get('result', {}), ensure_ascii=False)}\n")

                f.write(f"\n🤖 Agent:\n{agent_response}\n")

                if session_state:
                    f.write(f"\n📊 Session 狀態:\n")
                    f.write(f"  - 階段: {session_state.get('step')}\n")
                    f.write(f"  - 已回答: {session_state.get('answers_count', 0)}/5\n")
                    if session_state.get('color_result_id'):
                        f.write(f"  - 色系: {session_state.get('color_result_id')}\n")

                if error:
                    f.write(f"\n❌ 錯誤:\n{error}\n")

                f.write(f"{'='*80}\n")

        except Exception as e:
            logger.error(f"Failed to log conversation: {e}", exc_info=True)

    def get_session_logs(self, session_id: str) -> List[Dict]:
        """取得特定 session 的所有日誌

        Args:
            session_id: Session ID

        Returns:
            日誌記錄列表
        """
        # 檔名格式: YYYYMMDD_HHMMSS_{session_id}.jsonl
        # 使用 glob 找出該 session 的檔案
        existing_files = list(self.log_dir.glob(f"*{session_id}.jsonl"))
        if not existing_files:
            return []

        log_file = existing_files[0]
        logs = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to read session logs: {e}")

        return logs

    def list_sessions(self) -> List[str]:
        """列出所有有日誌的 session

        Returns:
            Session ID 列表
        """
        sessions = []
        for log_file in self.log_dir.glob("*.jsonl"):
            sessions.append(log_file.stem)
        return sorted(sessions)
