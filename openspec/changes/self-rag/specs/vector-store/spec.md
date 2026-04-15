# Vector Store Specification

## Overview

Dual-storage vector store: LanceDB (primary, fast) + MongoDB (backup, durable).

## Architecture

```
BGE Embeddings
    ↓
LanceDB (primary)  ← Direct search queries
    ↓ (on-write sync)
MongoDB (backup)   ← Disaster recovery, periodic validation
```

## LanceDB Schema

LanceDB table stores vectorized chunks with metadata:

```python
{
    "text": "What is hypertension?",
    "vector": [0.1, 0.2, ...],              # 1024-dim BGE embedding
    "file_id": "PRP_001",                   # Source: PRP_001.csv
    "source_language": "zh",                # "zh" or "en"
    "source_type": "jti_knowledge",         # "jti_knowledge" or "hciot_knowledge"
    "chunk_index": 0,                       # Position in document
    "file_fingerprint": "sha256:abc123",    # For change detection
    "metadata": {
        "path": "data/jti_knowledge/PRP_001.csv",
        "created_at": "2026-04-15T00:00:00",
        "updated_at": "2026-04-15T00:00:00"
    }
}
```

## MongoDB Schema (Backup)

Same schema as LanceDB for sync/recovery:

```javascript
db.embedding_chunks.insertOne({
    text: "What is hypertension?",
    vector: [0.1, 0.2, ...],
    file_id: "PRP_001",
    source_language: "zh",
    source_type: "jti_knowledge",
    chunk_index: 0,
    file_fingerprint: "sha256:abc123",
    metadata: {...},
    lancedb_synced_at: ISODate()  // For sync tracking
})
```

## API Contract

```python
class VectorStore:
    async def search(
        self,
        query_embedding: np.ndarray,  # 1024-dim
        top_k: int = 5,
        language: str = "zh",
        source_type: Optional[str] = None,
        min_similarity: float = 0.3
    ) -> List[SearchResult]:
        """Search LanceDB for similar chunks.
        
        Returns:
            [
                SearchResult(
                    text="...",
                    vector=[...],
                    file_id="PRP_001",
                    similarity=0.82
                ),
                ...
            ]
        """
    
    async def insert_chunks(
        self,
        chunks: List[ChunkRecord]
    ) -> int:
        """Insert chunks to LanceDB and sync to MongoDB.
        
        Returns:
            Number of chunks inserted
        """
    
    async def delete_by_file(
        self,
        file_id: str,
        source_type: str
    ) -> int:
        """Delete all chunks from a file (for updates)."""
    
    async def sync_to_mongodb(self) -> int:
        """Sync all LanceDB records to MongoDB backup.
        
        Returns:
            Number of records synced
        """
    
    async def get_stats(self) -> Dict:
        """Return storage statistics."""
        # Returns: {
        #   "total_chunks": 15000,
        #   "by_language": {"zh": 8000, "en": 7000},
        #   "by_source": {"jti_knowledge": 10000, "hciot_knowledge": 5000},
        #   "lancedb_records": 15000,
        #   "mongodb_backup_synced_at": "2026-04-15T00:00:00"
        # }
```

## Search Algorithm

### Similarity Computation

LanceDB uses:
- **Vector**: L2 distance (Euclidean)
- **ANN**: Approximate Nearest Neighbor search (fast)
- **Result**: Top K closest matches

```python
# LanceDB handles this natively:
table.search(query_embedding).limit(top_k).to_list()
```

### Filtering

Pre-filter by metadata before search:

```python
table.search(query_embedding) \
    .where(f"source_language == '{language}'") \
    .limit(top_k) \
    .to_list()
```

## Configuration

```python
# .env
LANCEDB_PATH=/data/lancedb           # Local LanceDB directory
LANCEDB_TABLE_NAME=knowledge         # Table name in LanceDB
MONGODB_BACKUP_ENABLED=true          # Enable MongoDB sync
MONGODB_BACKUP_SYNC_INTERVAL=3600    # Sync every hour
VECTOR_SEARCH_TOP_K=5
VECTOR_SEARCH_MIN_SIMILARITY=0.3
```

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_search_returns_top_k():
    store = VectorStore()
    query_embedding = np.random.randn(1024).astype(np.float32)
    query_embedding = query_embedding / np.linalg.norm(query_embedding)  # Normalize
    results = await store.search(query_embedding, top_k=5)
    assert len(results) <= 5

@pytest.mark.asyncio
async def test_search_with_language_filter():
    store = VectorStore()
    query_embedding = np.random.randn(1024).astype(np.float32)
    query_embedding = query_embedding / np.linalg.norm(query_embedding)
    results = await store.search(query_embedding, language="zh")
    assert all(r.source_language == "zh" for r in results)

@pytest.mark.asyncio
async def test_insert_and_search():
    store = VectorStore()
    chunk = ChunkRecord(
        text="test content",
        vector=np.random.randn(1024).astype(np.float32),
        file_id="TEST_001",
        source_language="zh",
        source_type="jti_knowledge",
        chunk_index=0,
        file_fingerprint="sha256:test"
    )
    inserted = await store.insert_chunks([chunk])
    assert inserted == 1
```

### Integration Tests

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_lancedb_and_mongodb_sync():
    store = VectorStore()
    # Insert chunk to LanceDB
    # Sync to MongoDB
    # Query both, verify same results
    lancedb_results = await store.search(...)
    mongodb_backup = await store._get_mongodb_backup(...)
    assert len(lancedb_results) == len(mongodb_backup)
```

## Performance Targets

- Search (top-5): <50ms (LanceDB ANN)
- Insert batch (1000): <2 seconds
- Sync to MongoDB: <5 seconds (for 10k records)
