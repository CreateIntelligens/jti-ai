"""
Gemini API 整合服務（使用新版 google-genai SDK）

職責：
1. 初始化 Gemini client
2. 提供 Main Agent 呼叫介面
3. 提供 retry / run_sync 工具函數
"""

import asyncio
import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)

# client 由 init_gemini_client() 在 startup 時從 registry 設定
client = None


def init_gemini_client():
    """從 registry 取得 default client，設定 module-level client 變數。"""
    global client
    from app.services.gemini_clients import get_default_client
    try:
        client = get_default_client()
        logger.info("Gemini client initialized from registry")
    except ValueError:
        logger.warning("GEMINI_API_KEYS not found - Gemini client not initialized")


async def run_sync(fn: Callable[..., T], *args) -> T:
    """Run a synchronous function in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(fn, *args)


def gemini_with_retry(fn: Callable[[], T], retries: int = 3, base_delay: float = 2.0) -> T:
    """
    呼叫 Gemini API 並在 503 UNAVAILABLE 時自動重試。

    Args:
        fn: 呼叫 Gemini 的 lambda，例如 lambda: chat.send_message(msg)
        retries: 最多重試次數（不含第一次）
        base_delay: 第一次重試等待秒數，之後線性增加（2s, 4s, 6s...）
    """
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            is_503 = "503" in err_str or "UNAVAILABLE" in err_str
            if not is_503 or attempt == retries:
                raise
            wait = base_delay * (attempt + 1)
            logger.warning(
                "[Gemini] 503 UNAVAILABLE，第 %d/%d 次重試，等待 %.0fs...",
                attempt + 1, retries, wait,
            )
            time.sleep(wait)
    # Unreachable: the loop always returns or raises
    raise RuntimeError("gemini_with_retry: unexpected exit")
