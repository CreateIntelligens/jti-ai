"""判斷使用者訊息是否表達自傷意圖：先問 Jev，Jev 失敗或逾時才問 Clef，都失敗才用正規表達式。

正規表達式漏判隱喻（「睡著就不要再醒來」「去找我阿嬤了」），也會把「笑到想死」
「跳樓大拍賣」當成危機，所以交給分類模型判斷。

每個模型的時限 0.8 秒（2026-10-14 開發機實測 Jev p95 約 0.3 秒），判斷和主模型同時跑，
主模型最快也要約 1.8 秒，所以不會拉長回覆時間。

只送單句會漏掉分成幾句說的危機（「我手邊有一整罐安眠藥」→「今晚就全部吃掉」，
單句 0.07、附前文 0.93），所以附上最近幾句使用者訊息。
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time

import httpx

from app.services.crisis_reply import is_self_harm_message

logger = logging.getLogger(__name__)

_DEFAULT_JEV_URL = "https://api.typesafe.ai/v1/systemone"
_DEFAULT_TIMEOUT_SECONDS = 0.8
_THRESHOLD = 0.5
_QUESTIONS = {
    "self_harm": {
        "type": "noul",
        "instructions": "使用者本人是否表達自傷、輕生意念或計畫？",
        "criteria": {
            "true": "說話者本人現在想死、想自殺、想傷害自己（包含隱喻、委婉說法、網路縮寫如 kms），或透露自傷方法、計畫、準備工具（如囤藥、買木炭、備刀），或已經做出自傷行為（如已吞下過量藥物）",
            "false": "抱怨、誇飾或玩笑、廣告用語、新聞或作品情節、單純情緒低落、詢問一般用藥或專線資訊、談論他人、明確否認或已過去的念頭",
        },
    }
}


def _providers() -> list[tuple[str, str, str, str]]:
    """回傳 (名稱, 端點, model, key)，依序嘗試；沒設定的跳過。"""
    providers = []
    jev_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if jev_key:
        jev_url = os.getenv("JEV_URL", "").strip() or _DEFAULT_JEV_URL
        providers.append(("jev", jev_url, "jev-latest", jev_key))
    clef_url = os.getenv("CLEF_URL", "").strip()
    if clef_url:
        providers.append(("clef", clef_url, "clef-flash", os.getenv("CLEF_API_KEY", "").strip()))
    return providers


def _timeout_seconds() -> float:
    try:
        value = float(os.getenv("SELF_HARM_CLASSIFIER_TIMEOUT", _DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


async def _ask(
    client: httpx.AsyncClient,
    url: str,
    model: str,
    key: str,
    state: dict,
) -> float:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    payload = {"model": model, "state": state, "questions": _QUESTIONS}
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    answer = (resp.json().get("answers") or {}).get("self_harm")
    probability = answer.get("noul") if isinstance(answer, dict) else None
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise ValueError("response is missing the self_harm probability")
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("self_harm probability is out of range")
    return float(probability)


async def _ask_logged(
    client: httpx.AsyncClient,
    provider: tuple[str, str, str, str],
    state: dict,
    timeout: float,
) -> bool | None:
    name, url, model, key = provider
    started = time.monotonic()
    try:
        # httpx 的 timeout 是每個階段各自計時，用 wait_for 才是整段的上限
        probability = await asyncio.wait_for(_ask(client, url, model, key, state), timeout)
    except Exception as exc:
        logger.warning("[SelfHarm] %s 判斷失敗: %s", name, type(exc).__name__)
        return None
    logger.info("[SelfHarm] %s p=%.2f %.0fms", name, probability, (time.monotonic() - started) * 1000)
    return probability >= _THRESHOLD


async def classify_self_harm(
    message: str,
    recent_user_messages: list[str] | None = None,
) -> bool | None:
    """依序問設定的模型，第一個有回答的就採用；全部失敗或都沒設定回 None。"""
    providers = _providers()
    if not message or not providers:
        return None
    state: dict = {"message": message}
    if recent_user_messages:
        state["recent_user_messages"] = recent_user_messages
    timeout = _timeout_seconds()
    async with httpx.AsyncClient() as client:
        for provider in providers:
            result = await _ask_logged(client, provider, state, timeout)
            if result is not None:
                return result
    return None


async def detect_self_harm(message: str, recent_user_messages: list[str] | None = None) -> bool:
    result = await classify_self_harm(message, recent_user_messages)
    if result is None:
        return is_self_harm_message(message)
    return result
