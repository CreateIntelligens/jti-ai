"""
Session 管理服務

職責：
1. Session CRUD
2. 狀態機管理
3. 生命週期控制

注意：目前使用記憶體存儲，生產環境應該換成 Redis
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from app.models.session import Session, SessionStep, GameMode
from .session_state_mixin import SessionStateMixin
import logging

logger = logging.getLogger(__name__)


class SessionManager(SessionStateMixin):
    """Session 管理器（記憶體版本）"""

    def __init__(self, idle_timeout_minutes: int = 30):
        self._sessions: Dict[str, Session] = {}
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)

    def create_session(self, mode: GameMode = GameMode.COLOR, language: str = "zh") -> Session:
        """建立新 session"""
        session = Session(mode=mode, language=language)
        self._sessions[session.session_id] = session
        logger.info(f"Created session: {session.session_id} (language={language})")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """取得 session"""
        session = self._sessions.get(session_id)

        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        # 檢查是否 timeout
        if self._is_expired(session):
            logger.info(f"Session expired: {session_id}")
            self.delete_session(session_id)
            return None

        return session

    def update_session(self, session: Session) -> Session:
        """更新 session"""
        session.update_timestamp()
        self._sessions[session.session_id] = session
        logger.info(f"Updated session: {session.session_id}, step={session.step}")
        return session

    def delete_session(self, session_id: str) -> bool:
        """刪除 session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False

    def _is_expired(self, session: Session) -> bool:
        """檢查 session 是否過期"""
        return datetime.now() - session.updated_at > self.idle_timeout

    # === 輔助方法 ===

    def get_all_sessions(self) -> list[Session]:
        """取得所有 sessions（測試用）"""
        return list(self._sessions.values())

    def clear_expired_sessions(self) -> int:
        """清理過期 sessions"""
        expired_ids = [
            sid
            for sid, session in self._sessions.items()
            if self._is_expired(session)
        ]
        for sid in expired_ids:
            self.delete_session(sid)
        return len(expired_ids)
