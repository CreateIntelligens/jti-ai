"""Generic document-to-QA extraction flow for QA knowledge-base sub-apps."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from google.genai import types
from pydantic import BaseModel, Field

from app.models_config import DEFAULT_MODEL, fallback_chain
from app.services.gemini_service import (
    gemini_with_fallback as default_gemini_with_fallback,
    gemini_with_retry as default_gemini_with_retry,
    run_sync as default_run_sync,
)

logger = logging.getLogger(__name__)

BuildInstruction = Callable[[str, str, str], str]
GeminiFallback = Callable[[Callable[[str], Any], Sequence[str]], Any]
GeminiRetry = Callable[[Callable[[], Any]], Any]
RunSync = Callable[..., Awaitable[Any]]


class QaPair(BaseModel):
    q: str = Field(description="The voice-style oral question a user might ask.")
    a: str = Field(description="The detailed, complete, professional yet warm answer answering the question.")


class QaListSchema(BaseModel):
    qa_pairs: list[QaPair]


async def extract_qa_from_document(
    *,
    text: str,
    language: str = "zh",
    persona_text: str = "",
    role_scope_text: str = "",
    build_instruction: BuildInstruction,
    model_client: Any,
    models_to_try: Sequence[str] | None = None,
    default_persona: str = "你是一個智慧對話助理，任務是回答使用者的問題。",
    default_role_scope: str = "回答使用者的各種問題，並提供清楚、白話、好懂的說明。",
    gemini_with_fallback_func: GeminiFallback = default_gemini_with_fallback,
    gemini_with_retry_func: GeminiRetry = default_gemini_with_retry,
    run_sync_func: RunSync = default_run_sync,
    log_prefix: str = "[QA Extractor]",
) -> list[dict[str, str]]:
    """Call the configured LLM client to extract Q&A pairs from document text."""
    cleaned_text = (text or "").strip()
    if not cleaned_text:
        raise ValueError("Document text is empty")

    persona = persona_text or default_persona
    role_scope = role_scope_text or default_role_scope
    system_instruction = build_instruction(language, persona, role_scope)
    prompt = f"請從以下文件中擷取問答：\n\n```\n{cleaned_text}\n```"
    model_names = list(models_to_try or fallback_chain(DEFAULT_MODEL, model_client))

    def _call_gemini(model_name: str):
        logger.info("%s Calling model=%s (length=%d)", log_prefix, model_name, len(cleaned_text))
        config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=system_instruction)],
            response_mime_type="application/json",
            response_schema=QaListSchema,
            temperature=0.2,
        )
        return model_client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

    try:
        response = await run_sync_func(
            gemini_with_fallback_func,
            lambda model_name: gemini_with_retry_func(lambda: _call_gemini(model_name)),
            model_names,
        )

        raw_text = response.text
        if not raw_text:
            raise ValueError("Empty response received from LLM")

        data = json.loads(raw_text)
        qa_pairs = data.get("qa_pairs", [])

        result: list[dict[str, str]] = []
        for pair in qa_pairs:
            q = (pair.get("q") or "").strip()
            a = (pair.get("a") or "").strip()
            if q and a:
                result.append({"q": q, "a": a})

        logger.info("%s Successfully extracted %d Q&A pairs", log_prefix, len(result))
        return result

    except Exception as e:
        logger.error("%s Failed to extract Q&A from document: %s", log_prefix, e)
        raise
