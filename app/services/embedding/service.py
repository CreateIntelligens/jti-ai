import logging
from typing import Any, List, Optional, Union

import numpy as np
import torch
from app.services.embedding.errors import (
    EmbeddingModelError,
    EmbeddingEncodingError,
)


logger = logging.getLogger(__name__)

class EmbeddingService:
    _instance: Optional['EmbeddingService'] = None
    _model: Optional[Any] = None

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None
    ):
        import os
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self.device = device or os.getenv("EMBEDDING_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size or int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
        logger.debug(f"EmbeddingService config: {self.model_name} on {self.device}")

    @classmethod
    def get_instance(cls) -> 'EmbeddingService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def model(self):
        """Lazy-loaded model property."""
        if self.__class__._model is None:
            try:
                from FlagEmbedding import FlagModel
                logger.debug(f"Loading embedding model: {self.model_name}...")
                self.__class__._model = FlagModel(
                    self.model_name,
                    device=self.device,
                    use_fp16=(self.device == "cuda")
                )
                logger.debug("Embedding model loaded.")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise EmbeddingModelError(f"Could not load model {self.model_name}: {e}")
        return self.__class__._model


    def encode(
        self,
        texts: Union[str, List[str]],
        input_type: str = "document"
    ) -> np.ndarray:
        """Encode text(s) into embeddings."""
        if isinstance(texts, str):
            texts = [texts]
        
        try:
            # BGE-M3's encode() handles both single and batch
            return self.model.encode(
                texts,
                batch_size=self.batch_size,
                max_length=8192,
            )
        except (EmbeddingModelError, EmbeddingEncodingError):
            raise
        except Exception as e:
            logger.error(f"Encoding failed: {e}")
            raise EmbeddingEncodingError(f"Failed to encode texts: {e}")


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService.get_instance()
