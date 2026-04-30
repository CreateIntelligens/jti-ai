"""
Gemini Multi-Key Registry

讀取 GEMINI_API_KEYS（逗號分隔），為每把 key 建立 genai.Client。

用法：
    from app.services.gemini_clients import get_default_client
"""

import hashlib
import logging
import os

from google import genai

logger = logging.getLogger(__name__)

# store_name (e.g. "fileSearchStores/abc123") → genai.Client
_store_to_client: dict[str, genai.Client] = {}

# 所有 clients（按 key 順序）
_clients: list[genai.Client] = []

# key index → 顯示名稱
_key_names: list[str] = []

# Browser-supplied user keys are never persisted. Cache clients by hash only.
_user_key_clients: dict[str, genai.Client] = {}


def _parse_key_token(token: str, index: int) -> tuple[str, str]:
    """解析 'name:key' 或 'key' 格式，回傳 (name, api_key)。"""
    if ":" in token:
        name, api_key = token.split(":", 1)
        return name.strip(), api_key.strip()
    return f"Key #{index + 1}", token.strip()


def init_registry() -> None:
    """讀取所有 API keys，建立 genai.Client 列表。"""
    global _store_to_client, _clients, _key_names
    _store_to_client = {}
    _clients = []
    _key_names = []

    keys_raw = os.getenv("GEMINI_API_KEYS", "")
    tokens = [t.strip() for t in keys_raw.split(",") if t.strip()]

    if not tokens:
        logger.warning("未設定 GEMINI_API_KEYS")
        return

    seen_keys: set[str] = set()
    for i, token in enumerate(tokens):
        name, api_key = _parse_key_token(token, i)
        if api_key in seen_keys:
            continue
        seen_keys.add(api_key)
        try:
            c = genai.Client(api_key=api_key)
            _clients.append(c)
            _key_names.append(name)
        except Exception as e:
            logger.error(f"[Registry] {name} ({api_key[:8]}...) 初始化失敗（已跳過）: {e}")

    logger.info(f"[Registry] 共 {len(_clients)} 個 Gemini clients")


def register_store(store_name: str, client: genai.Client) -> None:
    """將新建的 store 註冊到 registry（runtime 新增 store 時呼叫）。"""
    _store_to_client[store_name] = client
    logger.info(f"[Registry] 已註冊 store: {store_name}")


def get_all_clients() -> list[genai.Client]:
    """回傳所有已註冊的 clients（供跨 key 操作使用）。"""
    return list(_clients)


def get_client_by_index(key_index: int) -> genai.Client:
    """根據 key index 取得 client（0-based）。"""
    if 0 <= key_index < len(_clients):
        return _clients[key_index]
    return get_default_client()


def get_client_for_api_key(api_key: str) -> genai.Client:
    """Return a Gemini client for a browser-supplied API key without storing the raw key."""
    normalized = (api_key or "").strip()
    if not normalized:
        return get_default_client()
    key_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    client = _user_key_clients.get(key_hash)
    if client is None:
        client = genai.Client(api_key=normalized)
        _user_key_clients[key_hash] = client
    return client


def get_key_count() -> int:
    """回傳已註冊的 key 數量。"""
    return len(_clients)


def get_key_names() -> list[str]:
    """回傳所有 key 的顯示名稱列表（順序對應 index）。"""
    return list(_key_names)


def get_client_index(client: genai.Client) -> int:
    """取得 client 在 registry 中的 index（找不到回傳 0）。"""
    try:
        return _clients.index(client)
    except ValueError:
        return 0


def get_store_key_index(store_name: str) -> int:
    """取得 store 對應的 key index（找不到回傳 0）。"""
    client = _store_to_client.get(store_name)
    return get_client_index(client) if client else 0


def get_client_for_store(store_name: str) -> genai.Client:
    """根據 store_name 取得對應的 client，找不到則回傳 default。"""
    return _store_to_client.get(store_name) or get_default_client()


def resolve_key_index_by_keyword(keyword: str) -> int:
    """Return the index of the first key whose name contains keyword (case-insensitive). Falls back to 0."""
    kw = keyword.lower()
    for i, name in enumerate(_key_names):
        if kw in name.lower():
            return i
    return 0


def get_default_client() -> genai.Client:
    """回傳第一把 key 的 client。"""
    if _clients:
        return _clients[0]
    raise ValueError("No Gemini API keys available (set GEMINI_API_KEYS)")
