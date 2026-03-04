"""
Gemini Multi-Key Registry

讀取 GEMINI_API_KEYS（逗號分隔），為每把 key 建立 genai.Client，
自動掃描每把 key 擁有的 File Search Stores，建立 store_name → client mapping。

用法：
    from app.services.gemini_clients import get_client_for_store, get_default_client
"""

import logging
import os

from google import genai

logger = logging.getLogger(__name__)

# store_name (e.g. "fileSearchStores/abc123") → genai.Client
_store_to_client: dict[str, genai.Client] = {}

# 所有 clients（按 key 順序）
_clients: list[genai.Client] = []

# fallback client cache（避免每次呼叫 get_default_client 都新建）
_fallback_client: genai.Client | None = None


def init_registry() -> None:
    """讀取所有 API keys，建立 clients，掃描 stores 建立 mapping。"""
    global _store_to_client, _clients, _fallback_client
    _store_to_client = {}
    _clients = []
    _fallback_client = None

    # 優先讀 GEMINI_API_KEYS（逗號分隔），fallback 到 GEMINI_API_KEY
    keys_raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]

    if not keys:
        logger.warning("未設定 GEMINI_API_KEYS 或 GEMINI_API_KEY")
        return

    for i, key in enumerate(keys):
        try:
            c = genai.Client(api_key=key)
            _clients.append(c)

            # 掃描此 key 下的所有 stores
            stores = list(c.file_search_stores.list())
            logger.info(
                f"[Registry] Key #{i+1} ({key[:8]}...): 發現 {len(stores)} 個 stores"
            )
            for s in stores:
                logger.info(f"  - {s.name} ({s.display_name})")
                _store_to_client[s.name] = c
        except Exception as e:
            logger.error(f"[Registry] Key #{i+1} ({key[:8]}...) 初始化失敗: {e}")

    logger.info(f"[Registry] 共 {len(_clients)} 個 clients, {len(_store_to_client)} 個 store mappings")


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


def get_key_count() -> int:
    """回傳已註冊的 key 數量。"""
    return len(_clients)


def get_client_index(client: genai.Client) -> int:
    """取得 client 在 registry 中的 index（找不到回傳 0）。"""
    try:
        return _clients.index(client)
    except ValueError:
        return 0


def get_store_key_index(store_name: str) -> int:
    """取得 store 對應的 key index（找不到回傳 0）。"""
    client = _store_to_client.get(store_name)
    if client:
        return get_client_index(client)
    return 0


def get_client_for_store(store_name: str) -> genai.Client:
    """根據 store_name 取得對應的 client，找不到則回傳 default。"""
    c = _store_to_client.get(store_name)
    if c:
        return c
    return get_default_client()


def get_default_client() -> genai.Client:
    """回傳第一把 key 的 client。"""
    if _clients:
        return _clients[0]
    # 最後手段：用 GEMINI_API_KEY 建一個（cache 起來避免重複建立）
    global _fallback_client
    if _fallback_client:
        return _fallback_client
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        _fallback_client = genai.Client(api_key=api_key)
        return _fallback_client
    raise ValueError("No Gemini API key available")
