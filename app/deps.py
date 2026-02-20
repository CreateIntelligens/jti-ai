"""
Shared application state and dependency functions for routers.

All mutable globals are stored here so that routers can import them
without circular imports with main.py.
"""

import hashlib
import logging
from typing import Dict, Optional

from fastapi import HTTPException

from .core import FileSearchManager
from .api_keys import APIKeyManager
from .services.session.session_manager_factory import get_conversation_logger, get_general_chat_session_manager

conversation_logger = get_conversation_logger()

# --- Mutable application state (set during startup) ---
manager: FileSearchManager | None = None
prompt_manager = None  # PromptManager
api_key_manager: APIKeyManager | None = None
general_session_manager = None  # GeneralChatSessionManager
user_managers: Dict[str, FileSearchManager] = {}


def init_managers():
    """Called from app startup event to initialise managers."""
    global manager, prompt_manager, api_key_manager, general_session_manager
    try:
        manager = FileSearchManager()
        from .prompts import PromptManager
        prompt_manager = PromptManager()
        api_key_manager = APIKeyManager()
        general_session_manager = get_general_chat_session_manager()
        if general_session_manager:
            print("[Startup] ✅ GeneralChatSessionManager (MongoDB) 已啟用")
        else:
            print("[Startup] ⚠️ GeneralChatSessionManager 未啟用，使用記憶體模式")
    except ValueError as e:
        print(f"警告: {e}")


def _get_or_create_manager(user_api_key: Optional[str] = None, session_id: Optional[str] = None) -> FileSearchManager:
    """
    根據 session_id 或 API Key 取得或建立 Manager

    優先順序：
    1. session_id（多用戶場景）
    2. user_api_key（API Key 場景）
    3. 全域 manager（預設）
    """
    # 1. 如果有 session_id，用 session_id 隔離
    if session_id:
        if session_id not in user_managers:
            if not manager:
                raise HTTPException(status_code=500, detail="未設定 API Key")
            # 複製全域 manager 的 API key 建立新實例
            new_mgr = FileSearchManager(api_key=manager.api_key if hasattr(manager, 'api_key') else None)

            # 嘗試從 MongoDB 恢復 session
            if general_session_manager:
                saved_session = general_session_manager.get_session(session_id)
                if saved_session:
                    history_contents = FileSearchManager._build_history_contents(
                        saved_session.get("chat_history", [])
                    )
                    new_mgr.start_chat(
                        saved_session["store_name"],
                        saved_session.get("model", "gemini-2.5-flash"),
                        system_instruction=saved_session.get("system_instruction"),
                        history=history_contents,
                    )
                    print(f"[Session] 從 MongoDB 恢復 Session: {session_id[:8]}... (歷史 {len(history_contents)} 則)")

            user_managers[session_id] = new_mgr
            if not (general_session_manager and general_session_manager.get_session(session_id)):
                print(f"[Session] 建立新的 Session Manager: {session_id[:8]}...")
        return user_managers[session_id]

    # 2. 如果有 user_api_key，用 API Key hash 隔離
    if user_api_key:
        key_hash = hashlib.sha256(user_api_key.encode()).hexdigest()
        if key_hash not in user_managers:
            try:
                user_managers[key_hash] = FileSearchManager(api_key=user_api_key)
                print(f"[Session] 建立新的 API Key Manager: {key_hash[:8]}...")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"無效的 API Key: {e}")
        return user_managers[key_hash]

    # 3. 使用預設的全域 manager
    if not manager:
        raise HTTPException(status_code=500, detail="未設定 API Key")
    return manager
