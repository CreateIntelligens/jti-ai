import re
import logging
from typing import List

logger = logging.getLogger(__name__)

# Rough token estimation ratios
# Chinese: ~1 char ≈ 1 token; English: ~4 chars ≈ 1 token
_CJK_RANGE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')


def _estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    Chinese characters count as ~1 token each.
    Non-CJK characters count as ~1 token per 4 characters.
    """
    cjk_count = len(_CJK_RANGE.findall(text))
    non_cjk_count = len(text) - cjk_count
    return cjk_count + max(1, non_cjk_count // 4) if non_cjk_count else cjk_count


class SemanticChunker:
    """Chunks text into semantically meaningful segments for vector indexing."""

    def __init__(self, chunk_size_tokens: int = 500, chunk_overlap_tokens: int = 50):
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens

    def chunk_text(self, text: str) -> List[str]:
        """
        Splits text into chunks, prioritizing sentence boundaries (Zh/En).
        Chunks overlap by `chunk_overlap_tokens` to preserve cross-boundary context.

        Args:
            text: The raw text to chunk.

        Returns:
            List[str]: A list of text chunks.
        """
        if not text:
            return []

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Split into sentences (supports Chinese and English punctuation)
        sentences = re.split(r'(?<=[。！？；.!?;])\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: List[str] = []
        current_sentences: List[str] = []
        current_token_counts: List[int] = []  # parallel to current_sentences
        current_tokens = 0

        for sentence in sentences:
            sent_tokens = _estimate_tokens(sentence)

            # Handle extremely long sentences by hard-wrapping with overlap
            if sent_tokens > self.chunk_size_tokens:
                if current_sentences:
                    chunks.append(" ".join(current_sentences))
                    current_sentences = []
                    current_token_counts = []
                    current_tokens = 0

                char_limit = self._tokens_to_chars(sentence, self.chunk_size_tokens)
                overlap_chars = self._tokens_to_chars(sentence, self.chunk_overlap_tokens)
                step = max(1, char_limit - overlap_chars)

                for i in range(0, len(sentence), step):
                    chunks.append(sentence[i:i + char_limit])
                continue

            # Check if adding this sentence exceeds target chunk size
            if current_tokens + sent_tokens > self.chunk_size_tokens and current_sentences:
                chunks.append(" ".join(current_sentences))

                # Overlap: carry trailing sentences using cached token counts
                overlap_sentences: List[str] = []
                overlap_counts: List[int] = []
                overlap_tokens = 0
                for s, s_tokens in zip(reversed(current_sentences), reversed(current_token_counts)):
                    if overlap_tokens + s_tokens > self.chunk_overlap_tokens:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_counts.insert(0, s_tokens)
                    overlap_tokens += s_tokens

                current_sentences = overlap_sentences
                current_token_counts = overlap_counts
                current_tokens = overlap_tokens

            current_sentences.append(sentence)
            current_token_counts.append(sent_tokens)
            current_tokens += sent_tokens

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks

    @staticmethod
    def _tokens_to_chars(text: str, token_count: int) -> int:
        """Estimate how many characters correspond to `token_count` tokens in `text`."""
        total_tokens = _estimate_tokens(text)
        if total_tokens == 0:
            return len(text)
        ratio = len(text) / total_tokens
        return max(1, int(ratio * token_count))
