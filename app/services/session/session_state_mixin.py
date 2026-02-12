"""
Shared session state transitions for both in-memory and MongoDB session managers.

This keeps the state machine logic in one place while letting each manager
implement its own persistence (in-memory dict vs MongoDB).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.session import Session, SessionStep


class SessionStateMixin:
    """
    Mixin that assumes the concrete class provides:
    - get_session(session_id) -> Optional[Session]
    - update_session(session: Session) -> Session
    """

    # === State transitions ===

    def start_quiz(
        self,
        session_id: str,
        selected_questions: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        session.step = SessionStep.QUIZ
        session.current_q_index = 0
        session.answers = {}
        session.current_question = None
        session.selected_questions = selected_questions
        session.color_scores = {}
        session.color_result_id = None
        session.color_result = None
        session.metadata["paused_quiz"] = False

        return self.update_session(session)

    def pause_quiz(self, session_id: str) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        session.step = SessionStep.WELCOME
        session.current_question = None
        session.metadata["paused_quiz"] = True

        return self.update_session(session)

    def resume_quiz(self, session_id: str) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        if not session.selected_questions:
            return session

        session.step = SessionStep.QUIZ
        session.metadata["paused_quiz"] = False
        if 0 <= session.current_q_index < len(session.selected_questions):
            session.current_question = session.selected_questions[session.current_q_index]

        return self.update_session(session)

    def set_current_question(
        self, session_id: str, question: Optional[Dict[str, Any]]
    ) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        session.current_question = question
        return self.update_session(session)

    def add_chat_message(self, session_id: str, role: str, content: str) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        session.chat_history.append({"role": role, "content": content})

        return self.update_session(session)

    def start_scoring(self, session_id: str) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        session.step = SessionStep.SCORING
        return self.update_session(session)

    def submit_answer(
        self, session_id: str, question_id: str, option_id: str
    ) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session or session.step != SessionStep.QUIZ:
            return None

        session.answers[question_id] = option_id
        session.current_q_index += 1
        return self.update_session(session)

    def complete_scoring(
        self,
        session_id: str,
        color_result_id: str,
        scores: Dict[str, int],
        color_result: Optional[Dict[str, Any]] = None,
    ) -> Optional[Session]:
        session = self.get_session(session_id)
        if not session:
            return None

        session.color_result_id = color_result_id
        session.color_scores = scores
        session.color_result = color_result
        session.step = SessionStep.DONE
        return self.update_session(session)

