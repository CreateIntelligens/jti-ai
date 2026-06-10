import logging
import os
from typing import Any, List, Optional, Union

import numpy as np

from app.services.embedding.errors import (
    EmbeddingModelError,
    EmbeddingEncodingError,
)


logger = logging.getLogger(__name__)


def _resolve_device(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    env_device = os.getenv("EMBEDDING_DEVICE")
    if env_device:
        return env_device
    try:
        import torch  # lazy: torch import alone costs ~500MB-1GB RSS; only pay it when actually deciding device
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _shutdown_loky_executor() -> None:
    """Shut down joblib/loky's reusable process pool if it was started.

    FlagEmbedding pulls in joblib, whose loky backend keeps a reusable
    executor backed by a POSIX semaphore (/dev/shm/sem.loky-*). It is only
    reclaimed by loky's own atexit, which races the multiprocessing
    resource_tracker and triggers a "leaked semaphore" warning. Stopping it
    during teardown reclaims the semaphore deterministically. No-op if loky
    was never used.
    """
    for path in ("joblib.externals.loky", "loky"):
        try:
            module = __import__(path, fromlist=["get_reusable_executor"])
            module.get_reusable_executor().shutdown(wait=True, kill_workers=True)
            return
        except Exception:
            continue


class EmbeddingService:
    _instance: Optional['EmbeddingService'] = None
    _model: Optional[Any] = None

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None
    ):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        self.device = _resolve_device(device)
        self.batch_size = batch_size or int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
        logger.debug(f"EmbeddingService config: {self.model_name} on {self.device}")

    @classmethod
    def get_instance(cls) -> 'EmbeddingService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def release(cls) -> bool:
        """Release the shared embedding model and stop its multiprocess pool.

        FlagModel spawns a multiprocessing pool whose semaphores are only
        reclaimed via stop_self_pool(). Relying on __del__ at interpreter
        shutdown races the resource_tracker and emits a "leaked semaphore"
        UserWarning, so we stop the pool explicitly during teardown.

        Returns True if a loaded model was released, False if nothing to do.
        """
        model = cls._model
        if model is None:
            cls._instance = None
            return False

        stop_self_pool = getattr(model, "stop_self_pool", None)
        if callable(stop_self_pool):
            stop_self_pool()

        _shutdown_loky_executor()

        cls._model = None
        cls._instance = None
        return True

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
