"""公開 topics 端點的 Redis 讀取快取。

topics 是低頻寫、高頻讀的資料（每次聊天頁載入都打），但每次讀取都要付一趟
跨區 DocumentDB 往返（經 SSH 跳板，實測 ~330ms）。這層快取把穩定狀態的讀取
降到個位數 ms，寫入時整個 app 的鍵一起失效。

與 session 快取一致：Redis 純粹是效能層，取不到就靜默降級直接查 Mongo，
不影響正確性。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_KEY_PREFIX = "topics"
# 後台寫入會主動失效；TTL 只負責限制失效失敗或外部寫入造成的陳舊時間。
_TTL_SECONDS = int(os.getenv("TOPICS_CACHE_TTL_SECONDS", "300"))

_client: Any = None
_client_initialized = False


def _get_client() -> Any | None:
    global _client, _client_initialized
    if _client_initialized:
        return _client

    _client_initialized = True
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis

        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        logger.info("Topics cache enabled")
        _client = client
    except Exception as exc:
        logger.warning("Topics cache disabled: %s", exc)
        _client = None
    return _client


def _cache_key(app: str, language: str, variant: str) -> str:
    return f"{_KEY_PREFIX}:{app}:{language}:{variant}"


def get_or_compute[T](
    app: str,
    language: str,
    variant: str,
    compute: Callable[[], T],
) -> T:
    """回傳快取值，未命中則呼叫 compute() 並寫回快取。

    Redis 任何異常都退回直接計算 —— 快取故障不該讓端點失敗。
    """
    client = _get_client()
    if client is None:
        return compute()

    key = _cache_key(app, language, variant)
    try:
        cached = client.get(key)
        if cached is not None:
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Topics cache read failed (%s): %s", key, exc)
        return compute()

    value = compute()
    try:
        client.set(key, json.dumps(value, ensure_ascii=False), ex=_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Topics cache write failed (%s): %s", key, exc)
    return value


def invalidate(app: str) -> None:
    """清掉該 app 所有語言/變體的 topics 快取（寫入後呼叫）。"""
    client = _get_client()
    if client is None:
        return

    pattern = f"{_KEY_PREFIX}:{app}:*"
    try:
        # scan_iter 避免 KEYS 在大 keyspace 上阻塞 Redis。
        keys = list(client.scan_iter(match=pattern, count=100))
        if keys:
            client.delete(*keys)
    except Exception as exc:
        logger.warning("Topics cache invalidation failed (%s): %s", pattern, exc)
