"""動態模型探索 — 從 Gemini API 取得可用模型清單，並以 TTL 快取結果。"""

import logging
import time
from dataclasses import dataclass

from google import genai

logger = logging.getLogger(__name__)

# 快取存活時間（秒）
_CACHE_TTL = 600

# 快取結構：{client_id_hash: (timestamp, list[ModelInfo])}
_cache: dict[int, tuple[float, list["ModelInfo"]]] = {}


@dataclass
class ModelInfo:
    """可用模型的精簡資訊。"""

    name: str  # 不含 'models/' 前綴
    display_name: str
    input_token_limit: int
    output_token_limit: int


def _sort_key(model: ModelInfo) -> tuple[int, str]:
    """排序鍵：flash-lite 優先 → flash（非 lite）→ pro → 其他。"""
    name = model.name.lower()
    if "flash" in name and "lite" in name:
        return (0, name)
    if "flash" in name and "lite" not in name:
        return (1, name)
    if "pro" in name:
        return (2, name)
    return (3, name)


def _model_name_without_prefix(name: str) -> str:
    return name.removeprefix("models/")


def get_available_models(client: genai.Client) -> list[ModelInfo]:
    """取得指定 client 可用的生成模型清單（含快取）。"""
    key = id(client)
    now = time.monotonic()

    # 檢查快取是否仍有效
    cached_entry = _cache.get(key)
    if cached_entry:
        cached_at, cached_models = cached_entry
        if now - cached_at < _CACHE_TTL:
            return cached_models

    try:
        raw_models = client.models.list()
    except Exception:
        logger.exception("取得模型清單失敗")
        return []

    results: list[ModelInfo] = []
    for raw_model in raw_models:
        # 僅保留支援 generateContent 且名稱包含 gemini 的模型
        if "generateContent" not in (raw_model.supported_actions or ()):
            continue
        if "gemini" not in raw_model.name.lower():
            continue

        # 排除非一般的對話模型（如含有 banana, tts, image, audio, embedding, robotics, computer-use, deep-research, aqa 等關鍵字）
        name_lower = raw_model.name.lower()
        disp_lower = (raw_model.display_name or "").lower()
        exclude_keywords = ["banana", "tts", "image", "audio", "embedding", "robotics", "computer-use", "deep-research", "aqa"]
        if any(kw in name_lower or kw in disp_lower for kw in exclude_keywords):
            continue

        name = _model_name_without_prefix(raw_model.name)

        results.append(
            ModelInfo(
                name=name,
                display_name=raw_model.display_name or name,
                input_token_limit=raw_model.input_token_limit or 0,
                output_token_limit=raw_model.output_token_limit or 0,
            )
        )

    results.sort(key=_sort_key)

    # 寫入快取
    _cache[key] = (now, results)
    return results
