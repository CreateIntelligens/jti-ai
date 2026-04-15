import re
import logging
from typing import List

logger = logging.getLogger(__name__)

class SemanticChunker:
    """Chunks text into semantically meaningful segments for vector indexing."""
    
    def __init__(self, chunk_size_chars: int = 500, chunk_overlap_chars: int = 50):
        # Using characters as a proxy for tokens for local implementation
        self.chunk_size_chars = chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    def chunk_text(self, text: str) -> List[str]:
        """
        Splits text into chunks, prioritizing sentence boundaries (Zh/En).
        
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
        # Positive lookbehind for sentence-ending markers
        sentences = re.split(r'(?<=[。！？；.!?;])\s*', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Handle extremely long sentences by hard-wrapping
            if len(sentence) > self.chunk_size_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # Split long sentence into fixed-width units
                for i in range(0, len(sentence), self.chunk_size_chars):
                    chunks.append(sentence[i:i + self.chunk_size_chars])
                continue

            # Check if adding this sentence exceeds target chunk size
            if len(current_chunk) + len(sentence) + 1 > self.chunk_size_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
                    
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
