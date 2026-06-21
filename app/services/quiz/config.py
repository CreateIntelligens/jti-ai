from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


JTI_STORE_NAME = "__jti__"
HCIOT_STORE_NAME = "__hciot__"
ESG_STORE_NAME = "__esg__"


@dataclass
class QuizFlowConfig:
    session_manager_getter: Callable[[], Any]
    conversation_logger_getter: Callable[[], Any]
    tts_manager_getter: Optional[Callable[[], Any]] = None
    agent: Optional[Any] = None
    store_name: str = JTI_STORE_NAME
    mode: str = "jti"  # "jti", "hciot", "esg", or "general"
    copy_templates: Dict[str, Dict[str, str]] = field(default_factory=dict)
    tts_fn: Optional[Callable[[str, str], Any]] = None  # (text, language) -> tts
    keywords: List[str] = field(default_factory=list)
    negative_keywords: List[str] = field(default_factory=list)
