"""
Base Agent - 共用的 Gemini chat session 管理邏輯

提供 JTI MainAgent 與 HCIoT HciotMainAgent 共用的：
- Gemini chat session 建立與快取
- MongoDB 歷史同步（含背景非同步寫入）
- session 清除
"""

import asyncio
import logging
from typing import Any, Dict

from google.genai import types

from app.models.session import Session
import app.services.gemini_service as _gemini_service
from app.services.agent_utils import build_chat_history

logger = logging.getLogger(__name__)


class BaseAgent:
    """Gemini chat session 管理基底類別"""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._chat_sessions: Dict[str, Any] = {}

    # --- 子類必須實作 ---

    def _get_system_instruction(self, session: Session) -> str:
        raise NotImplementedError

    # --- 子類使用的 session_manager 屬性 ---
    # 子類應在 module level 設定 session_manager，
    # 並在需要時透過 self._session_manager 存取。

    @property
    def _session_manager(self):
        raise NotImplementedError

    # --- 共用 session 管理 ---

    def _get_or_create_chat_session(self, session: Session):
        """取得或建立持久 Gemini chat session"""
        sid = session.session_id
        if sid in self._chat_sessions:
            return self._chat_sessions[sid]

        history = build_chat_history(session.chat_history) if session.chat_history else []
        if history:
            logger.info(
                "從歷史恢復 chat session: %d 筆 (session=%s...)",
                len(history), sid[:8],
            )

        system_instruction = self._get_system_instruction(session)
        config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=system_instruction)],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        chat_session = _gemini_service.client.chats.create(
            model=self.model_name,
            config=config,
            history=history,
        )
        self._chat_sessions[sid] = chat_session
        return chat_session

    def _sync_history_to_db(self, session_id: str, user_message: str, assistant_message: str):
        """將 user/model 訊息同步到 MongoDB"""
        session = self._session_manager.get_session(session_id)
        if not session:
            return
        session.chat_history.append({"role": "user", "content": user_message})
        session.chat_history.append({"role": "assistant", "content": assistant_message})
        self._session_manager.update_session(session)

    def _sync_history_to_db_background(self, session_id: str, user_message: str, assistant_message: str):
        """背景非同步寫入 DB，不阻塞回應"""
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(
                None, self._sync_history_to_db, session_id, user_message, assistant_message,
            )
        except Exception:
            self._sync_history_to_db(session_id, user_message, assistant_message)

    def remove_session(self, session_id: str):
        """清除記憶體中的 chat session"""
        self._chat_sessions.pop(session_id, None)

    def remove_all_sessions(self):
        """清除所有記憶體中的 chat sessions"""
        count = len(self._chat_sessions)
        self._chat_sessions.clear()
        if count > 0:
            logger.info("已清除 %d 個 chat sessions", count)

    @staticmethod
    def _append_to_chat_history(chat_session, user_message: str, model_message: str):
        """將乾淨的 user/model 訊息追加到 SDK chat session 的內部歷史"""
        if hasattr(chat_session, '_curated_history'):
            chat_session._curated_history.append(
                types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
            )
            chat_session._curated_history.append(
                types.Content(role="model", parts=[types.Part.from_text(text=model_message)])
            )

    @staticmethod
    def _clean_enriched_history(chat_session, original_user_message: str):
        """將 enriched_message 替換回乾淨的 user_message，避免 KB 結果累積在歷史中"""
        if hasattr(chat_session, '_curated_history') and chat_session._curated_history:
            last_user = chat_session._curated_history[-2]
            if last_user.role == "user":
                last_user.parts = [types.Part.from_text(text=original_user_message)]
