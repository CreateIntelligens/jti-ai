class EmbeddingError(Exception):
    """Base class for embedding errors."""
    pass

class EmbeddingModelError(EmbeddingError):
    """Failed to load or initialize the embedding model."""
    pass

class EmbeddingEncodingError(EmbeddingError):
    """Failed to encode text into embeddings."""
    pass
