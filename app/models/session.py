"""
Session 模型定義

根據系統設計文件，Session 是流程狀態機，不是聊天紀錄。
LLM 不得根據對話內容自行判斷進度，只能依賴 session。
"""

from enum import Enum
from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import uuid


class SessionStep(str, Enum):
    """Session 狀態定義"""
    WELCOME = "WELCOME"     # 初始狀態，歡迎使用者
    QUIZ = "QUIZ"           # 問答中
    SCORING = "SCORING"     # 計分中（不可與 user 互動）
    RECOMMEND = "RECOMMEND" # 商品推薦
    DONE = "DONE"          # 流程完成


# 動態 TTL：依 step 決定 session 存活時間。
# 配合 sessions 集合上的 expireAfterSeconds=0 TTL 索引，MongoDB 會在
# expires_at 到期後自動回收文件。
#
# 角色定位：session 建立即落庫（多 worker 共享狀態），TTL 負責回收。
# 純開頁、零對話的空 session 也會落庫，但同樣 1 天內由 TTL 回收，不長期積壓。
#   - WELCOME / DONE（未進行或已結束）：1 天回收
#   - QUIZ / SCORING / RECOMMEND（測驗進行中）：1 天，保障中斷續答
_SHORT_SESSION_TTL = timedelta(days=1)
_ACTIVE_SESSION_TTL = timedelta(days=1)
_TTL_BY_STEP: Dict[str, timedelta] = {
    SessionStep.WELCOME.value: _SHORT_SESSION_TTL,    # 未進行/僅開場
    SessionStep.DONE.value: _SHORT_SESSION_TTL,       # 流程已完成
    SessionStep.QUIZ.value: _ACTIVE_SESSION_TTL,      # 答題中，保障續答
    SessionStep.SCORING.value: _ACTIVE_SESSION_TTL,   # 計分中（短暫過渡，從寬）
    SessionStep.RECOMMEND.value: _ACTIVE_SESSION_TTL,  # 推薦階段
}


def compute_expires_at(step: "SessionStep", now: Optional[datetime] = None) -> datetime:
    """依 session 步驟計算動態過期時間點。"""
    base = now or datetime.now()
    step_value = step.value if isinstance(step, SessionStep) else str(step)
    return base + _TTL_BY_STEP.get(step_value, _SHORT_SESSION_TTL)


class Session(BaseModel):
    """Session 資料結構"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step: SessionStep = SessionStep.WELCOME
    language: str = "zh"  # 語言設定 (zh/en)

    # 測驗相關
    current_q_index: int = 0      # 目前題目索引
    answers: Dict[str, str] = Field(default_factory=dict)  # {question_id: option_id}
    selected_questions: Optional[List[Dict[str, Any]]] = None  # 本次測驗隨機選中的題目列表

    # 結果相關
    quiz_result_id: Optional[str] = None  # 測驗結果，例如 "analyst"
    quiz_scores: Dict[str, int] = Field(default_factory=dict)  # 各維度得分
    quiz_result: Optional[Dict[str, Any]] = None  # 測驗結果內容（文案與推薦色）

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
