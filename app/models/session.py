"""
Session 模型定義

根據系統設計文件，Session 是流程狀態機，不是聊天紀錄。
LLM 不得根據對話內容自行判斷進度，只能依賴 session。
"""

from enum import Enum
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class SessionStep(str, Enum):
    """Session 狀態定義"""
    QUIZ = "QUIZ"           # 問答中
    SCORING = "SCORING"     # 計分中（不可與 user 互動）
    RECOMMEND = "RECOMMEND" # 商品推薦
    DONE = "DONE"          # 流程完成


class GameMode(str, Enum):
    """遊戲模式"""
    MBTI = "MBTI"           # MBTI 測驗


class Session(BaseModel):
    """Session 資料結構"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: GameMode = GameMode.MBTI
    step: SessionStep = SessionStep.QUIZ

    # 測驗相關
    quiz_id: str = "mbti_quick"  # 使用的題庫 ID
    current_q_index: int = 0      # 目前題目索引
    answers: Dict[str, str] = Field(default_factory=dict)  # {question_id: option_id}

    # 結果相關
    persona: Optional[str] = None  # MBTI 類型，例如 "INTJ"
    persona_scores: Optional[Dict[str, int]] = None  # 各維度得分

    # 推薦相關
    recommended_products: Optional[list] = None

    # 時間戳記
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 對話歷史（用於 LLM 上下文）
    chat_history: list = Field(default_factory=list)  # [{role: "user/assistant", content: "..."}]

    # 目前題目（快取，避免重複查詢）
    current_question: Optional[Dict[str, Any]] = None

    # 額外資料（可選）
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def update_timestamp(self):
        """更新時間戳記"""
        self.updated_at = datetime.now()

    def can_interact(self) -> bool:
        """判斷是否可以與 user 互動"""
        return self.step != SessionStep.SCORING

    def is_quiz_complete(self, total_questions: int) -> bool:
        """判斷測驗是否完成"""
        return len(self.answers) >= total_questions

    def model_dump(self, **kwargs):
        """序列化（處理 datetime）"""
        data = super().model_dump(**kwargs)
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data
