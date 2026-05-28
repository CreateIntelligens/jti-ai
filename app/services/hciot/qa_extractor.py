"""HCIoT document to structured Q&A extractor using Gemini API."""

import logging

from app.services._shared.qa_kb.extractor_base import (
    QaListSchema,
    QaPair,
    extract_qa_from_document as _extract_qa_from_document,
)
from app.services.gemini_clients import get_default_client
from app.services.gemini_service import (
    gemini_with_fallback,
    gemini_with_retry,
    run_sync,
)

logger = logging.getLogger(__name__)


def _build_extraction_instruction(language: str, persona_text: str, role_scope_text: str) -> str:
    if language == "zh":
        return f"""你是知識整理助理。你的任務是閱讀輸入的文件內容，並將其整理/拆解為多組口語化的問答對（Q&A）。

【前情提要 / 助理角色與服務範圍】：
這些問答對（Q&A）將會匯入至以下智慧助理的知識庫中，因此產出的問答對風格與內容必須與該助理的身份定位與服務範圍高度契合，避免偏題：
---
角色設定：
{persona_text}

服務範圍：
{role_scope_text}
---

請嚴格遵循以下規則：
1. 【保留既有問答】：如果輸入的文件本身就已經是問答格式（Q&A），請不要對其進行大規模重寫或大改。你的首要任務是修正其中的文字、錯別字或明顯的邏輯錯誤，儘可能保留原有的問題與答案內容。
2. 【忠於原文】：問答組數**完全取決於原文實際包含的資訊量**。原文有幾個獨立知識點就產出幾組問答，不要為了湊數量而捏造、衍生或拆分內容。寧可少而精準，也不要多而失真。
3. 【口語發問】：問題必須是以一般使用者口頭詢問的口語化語氣（例如：「我該怎麼做？」、「這個要怎麼處理？」），並與上述前情提要高度相關。
4. 【完整回答】：答案必須完整、語氣溫和專業且白話好懂，能夠單獨被閱讀且理解。絕對不可使用「請參考前文」或省略關鍵上下文。
5. 【涵蓋重點】：全面涵蓋原文的重要知識點，避免遺漏關鍵資訊。
6. 【獨立完備】：每組問答必須是完全獨立自適應的，答案內若提及專有名詞，需有簡短說明。
7. 【上限】：單次最多產出 20 組。若原文資訊豐富到超過 20 組，請挑選最重要的 20 組。下限沒有限制，原文只有 1 組就回 1 組，0 組就回空陣列。
"""
    else:
        return f"""You are a knowledge extraction assistant. Your task is to read the input document and extract/format structured Q&A pairs.

[Context, Assistant Role & Scope]:
These Q&A pairs will be imported into the knowledge base of the following smart assistant. The extracted Q&A pairs must align with this role and scope to avoid off-topic subjects:
---
Persona:
{persona_text}

Role Scope:
{role_scope_text}
---

Please strictly follow these rules:
1. [Preserve Existing Q&As]: If the input document is already in a Q&A format, do not rewrite or modify it drastically. Your primary goal is to correct typos, grammar, or logical issues while preserving the original questions and answers as much as possible.
2. [Faithful to Source]: The number of Q&A pairs is **entirely determined by the actual information in the source**. Output exactly as many pairs as the source contains distinct knowledge points — do not fabricate, derive, or split content to inflate the count. Prefer fewer accurate pairs over more pairs that distort the source.
3. [Oral Questions]: Questions must be written in an oral, natural tone as if a user is asking (e.g., 'What should I do?', 'How do I handle this?'), aligning with the context above.
4. [Complete Answers]: Answers must be complete, professional yet warm, and readable on their own. Never reply with "refer to previous section" or omit key context.
5. [Key Points Coverage]: Cover all the main educational and factual points of the text comprehensively.
6. [Self-Contained]: Each Q&A pair must be completely self-contained. If specialized terms are used in the answer, provide a brief explanation.
7. [Upper Bound Only]: Output at most 20 pairs per call. If the source has more, pick the 20 most important. There is no minimum — return 1 pair if the source only has 1, return an empty array if there is none.
"""


async def extract_qa_from_document(
    text: str,
    language: str = "zh",
    persona_text: str = "",
    role_scope_text: str = "",
) -> list[dict[str, str]]:
    """
    Call Gemini API to extract Q&A pairs from the document text.
    Returns a list of dicts: [{"q": "...", "a": "..."}, ...]
    """
    return await _extract_qa_from_document(
        text=text,
        language=language,
        persona_text=persona_text,
        role_scope_text=role_scope_text,
        build_instruction=_build_extraction_instruction,
        model_client=get_default_client(),
        gemini_with_fallback_func=gemini_with_fallback,
        gemini_with_retry_func=gemini_with_retry,
        run_sync_func=run_sync,
    )
