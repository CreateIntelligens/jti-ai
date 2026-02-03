"""
Session 管理服務

職責：
1. Session CRUD
2. 狀態機管理
3. 生命週期控制

注意：目前使用記憶體存儲，生產環境應該換成 Redis
"""

from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from app.models.session import Session, SessionStep, GameMode
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Session 管理器（記憶體版本）"""

    def __init__(self, idle_timeout_minutes: int = 30):
        self._sessions: Dict[str, Session] = {}
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)

    def create_session(self, mode: GameMode = GameMode.MBTI) -> Session:
        """建立新 session"""
        session = Session(mode=mode)
        self._sessions[session.session_id] = session
        logger.info(f"Created session: {session.session_id}")
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

    # === 狀態轉換方法 ===

    def start_quiz(self, session_id: str, selected_questions: Optional[List[Dict[str, Any]]] = None) -> Optional[Session]:
        """開始測驗"""
        session = self.get_session(session_id)
        if not session:
            return None

        session.step = SessionStep.QUIZ
        session.current_q_index = 0
        session.answers = {}
        session.current_question = None
        session.selected_questions = selected_questions  # 保存隨機選中的題目
        return self.update_session(session)

    def set_current_question(self, session_id: str, question: dict) -> Optional[Session]:
        """設定當前題目"""
        session = self.get_session(session_id)
        if not session:
            return None

        session.current_question = question
        return self.update_session(session)

    def add_chat_message(self, session_id: str, role: str, content: str) -> Optional[Session]:
        """加入對話訊息"""
        session = self.get_session(session_id)
        if not session:
            return None

        # 保留最近 10 筆對話
        session.chat_history.append({"role": role, "content": content})
        if len(session.chat_history) > 10:
            session.chat_history = session.chat_history[-10:]

        return self.update_session(session)

    def submit_answer(
        self, session_id: str, question_id: str, option_id: str
    ) -> Optional[Session]:
        """提交答案"""
        session = self.get_session(session_id)
        if not session or session.step != SessionStep.QUIZ:
            return None

        session.answers[question_id] = option_id
        session.current_q_index += 1
        return self.update_session(session)

    def start_scoring(self, session_id: str) -> Optional[Session]:
        """進入計分狀態"""
        session = self.get_session(session_id)
        if not session:
            return None

        session.step = SessionStep.SCORING
        return self.update_session(session)

    def complete_scoring(
        self, session_id: str, persona: str, scores: Dict[str, int]
    ) -> Optional[Session]:
        """完成計分"""
        session = self.get_session(session_id)
        if not session:
            return None

        session.persona = persona
        session.persona_scores = scores
        session.step = SessionStep.RECOMMEND
        return self.update_session(session)

    def save_recommendations(
        self, session_id: str, products: list
    ) -> Optional[Session]:
        """保存推薦結果"""
        session = self.get_session(session_id)
        if not session:
            return None

        session.recommended_products = products
        session.step = SessionStep.DONE
        return self.update_session(session)

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


# 全域 session manager 實例
session_manager = SessionManager()
