# Embedding Service Specification

## Overview

Local BGE embedding service using FlagEmbedding library (same as openVman).

## API Contract

```python
class EmbeddingService:
    async def embed(
        self,
        texts: List[str],
        input_type: Literal["document", "query"] = "document"
    ) -> np.ndarray:
        """Embed texts using BGE model.
        
        Args:
            texts: List of texts to embed
            input_type: "document" for knowledge chunks, "query" for user queries
        
        Returns:
            Embedding matrix (len(texts), 1024), float32
            Embeddings are L2-normalized by BGE model
        
        Raises:
            EmbeddingError: Model loading or encoding failure
        """
```

## Implementation

### 1. Model Loading

```python
from FlagEmbedding import BGEM3FlagModel

class EmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        # Lazy load on first use
        self._model: Optional[BGEM3FlagModel] = None
        self._model_name = model_name
        self._lock = threading.Lock()  # Thread-safe encoding
    
    def _ensure_model_loaded(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = BGEM3FlagModel(
                        self._model_name,
                        use_fp16=True,  # Use float16 to reduce memory
                        device="cuda" if torch.cuda.is_available() else "cpu"
                    )
```

### 2. Batch Encoding

```python
def encode(
    self,
    texts: List[str],
    input_type: str = "document"
) -> np.ndarray:
    """Encode texts using BGE model."""
    self._ensure_model_loaded()
    
    with self._lock:  # Thread-safe
        result = self._model.encode(
            texts,
            batch_size=32,  # Tune based on memory
            max_length=512  # Truncate long texts
        )
    
    # BGE returns dict with 'dense_vecs' (L2-normalized)
    dense_vectors = result["dense_vecs"]
    return np.array(dense_vectors, dtype=np.float32)
```

### 3. Error Handling

```python
class EmbeddingError(Exception):
    """Base embedding error"""

class EmbeddingModelError(EmbeddingError):
    """Model loading or inference failure"""

class EmbeddingEncodingError(EmbeddingError):
    """Text encoding failure (invalid input, etc.)"""
```

## Configuration

```python
# .env
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_BATCH_SIZE=32
EMBEDDING_MAX_LENGTH=512
EMBEDDING_DEVICE=cuda  # or "cpu"
```

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_embed_single_document():
    service = EmbeddingService()
    result = service.encode(["test text"], input_type="document")
    assert result.shape == (1, 1024)
    assert result.dtype == np.float32
    assert np.allclose(np.linalg.norm(result[0]), 1.0)  # L2-normalized

@pytest.mark.asyncio
async def test_embed_batch():
    service = EmbeddingService()
    texts = ["doc1", "doc2", "doc3"]
    result = service.encode(texts, input_type="document")
    assert result.shape == (3, 1024)
    assert all(np.allclose(np.linalg.norm(result[i]), 1.0) for i in range(3))

@pytest.mark.asyncio
async def test_thread_safe_encoding():
    # Multiple threads encoding in parallel
    service = EmbeddingService()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(service.encode, [f"text{i}"])
            for i in range(10)
        ]
        results = [f.result() for f in futures]
    assert len(results) == 10
```

## Performance Characteristics

- First call: ~2 seconds (model loading)
- Single text: ~10-50ms (depending on length)
- Batch (32 texts): ~50-100ms
- Throughput: 300-1000 texts/second (batch dependent)
- Memory: ~2GB (model + inference)

## Device Selection

```python
# Auto-detect device based on availability
if torch.cuda.is_available():
    device = "cuda"  # GPU (faster, ~3-5x speedup)
else:
    device = "cpu"   # CPU (slower, but works everywhere)
```
