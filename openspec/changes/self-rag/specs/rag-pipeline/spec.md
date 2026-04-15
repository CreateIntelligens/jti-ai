# RAG Pipeline Specification

## Overview

RAG pipeline replaces Gemini File Search with local BGE + LanceDB vector search.

## Pipeline Flow

```
User Query
    ↓
Embed with BGE (~100ms)
    ↓
Search LanceDB (<50ms)
    ↓
Format results
    ↓
Return kb_result + citations
    ↓
Pass to Chat Session Layer (Gemini LLM with persona)
```

## API Contract

```python
class RAGPipeline:
    async def retrieve(
        self,
        query: str,
        language: str = "zh",
        source_type: Optional[str] = None,
        top_k: int = 5
    ) -> RAGResult:
        """Retrieve relevant documents for a query.
        
        Returns:
            RAGResult(
                kb_result="Formatted text from top K chunks",
                citations=[
                    Citation(
                        file_id="PRP_001",
                        text="...",
                        similarity=0.82
                    ),
                    ...
                ],
                metadata={
                    "embedding_time_ms": 100,
                    "search_time_ms": 40,
                    "total_time_ms": 140,
                    "top_chunk_similarity": 0.82,
                    "embedding_version": "bge"
                }
            )
        """
    
    async def startup_backfill(self):
        """On startup: sync knowledge base to LanceDB.
        
        Workflow:
        1. Scan knowledge base directory
        2. For each CSV:
           a. Compute SHA256 fingerprint
           b. Check if already in LanceDB (by fingerprint)
           c. If new/changed: chunk text, embed with BGE, insert to LanceDB
        3. Sync LanceDB to MongoDB backup
        4. Log: "Backfilled 150 chunks from 3 files"
        """
```

## Integration with Routes

### Feature Flag Integration

```python
# app/routers/jti.py
if os.getenv("USE_SELF_RAG", "false").lower() == "true":
    # Use RAG pipeline (BGE + LanceDB)
    rag_pipeline = RAGPipeline()
    result = await rag_pipeline.retrieve(
        query,
        language=language,
        source_type="jti_knowledge"
    )
    kb_result = result.kb_result
    citations = result.citations
else:
    # Fall back to File Search (existing)
    file_search_tool = types.Tool(file_search=...)
```

### Output Format Compatibility

Both RAG and File Search return compatible format:

```python
{
    "kb_result": "Formatted knowledge base text (citations numbered)",
    "citations": [
        {
            "file_id": "PRP_001",
            "text": "Chunk content",
            "similarity": 0.82  # From RAG; not in File Search
        }
    ]
}
```

## Startup Backfill

### Execution

```python
# app/main.py
async def lifespan(app: FastAPI):
    # Startup
    if os.getenv("USE_SELF_RAG", "false").lower() == "true":
        rag_pipeline = RAGPipeline()
        await rag_pipeline.startup_backfill()
    
    yield
    
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)
```

### Backfill Logic

```python
async def startup_backfill(self):
    """
    1. Find all knowledge base files:
       - JTI: /data/jti_knowledge/*.csv
       - HCIoT: /data/hciot_knowledge/*.csv
    
    2. For each CSV:
       a. Read CSV
       b. Compute sha256(file_content)
       c. Query LanceDB for existing fingerprint
       d. If new/updated:
          - Chunk text (semantic chunks, ~500 tokens)
          - Batch embed with BGE (32 chunks/batch)
          - Insert to LanceDB (overwrite old chunks)
       e. Log: "PRP_001.csv: 12 chunks, 2 new"
    
    3. Sync LanceDB to MongoDB (backup)
       - Full table copy (upsert by file_id + chunk_index)
    
    4. Summary: "Backfill complete: 150 total chunks, 15 new"
    """
```

## Error Handling

```python
class RAGError(Exception):
    """Base RAG error"""

class EmbeddingFailedError(RAGError):
    """Query embedding failed"""

class SearchFailedError(RAGError):
    """LanceDB search failed"""

class BackfillFailedError(RAGError):
    """Startup backfill encountered errors"""
    # Log errors but don't crash startup
    # Fall back to File Search for problematic files
```

## Configuration

```python
# .env
USE_SELF_RAG=false              # Set true to enable RAG, false for File Search
RAG_TOP_K=5
RAG_MIN_SIMILARITY=0.3
RAG_CHUNK_SIZE_TOKENS=500
RAG_BACKFILL_BATCH_SIZE=32

# Paths
JTI_KNOWLEDGE_PATH=/data/jti_knowledge
HCIOT_KNOWLEDGE_PATH=/data/hciot_knowledge

# LanceDB
LANCEDB_PATH=/data/lancedb
LANCEDB_TABLE_NAME=knowledge

# MongoDB backup
MONGODB_BACKUP_ENABLED=true
MONGODB_BACKUP_SYNC_INTERVAL=3600
```

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_retrieve_returns_formatted_result():
    rag = RAGPipeline()
    result = await rag.retrieve("What is hypertension?")
    assert result.kb_result
    assert isinstance(result.citations, list)
    assert result.metadata["total_time_ms"] < 500

@pytest.mark.asyncio
async def test_retrieve_respects_language_filter():
    rag = RAGPipeline()
    result = await rag.retrieve("test", language="zh")
    assert all(c.source_language == "zh" for c in result.citations)

@pytest.mark.asyncio
async def test_retrieve_uses_source_type():
    rag = RAGPipeline()
    result = await rag.retrieve(
        "test",
        source_type="jti_knowledge"
    )
    assert all(c.source_type == "jti_knowledge" for c in result.citations)
```

### Integration Tests

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_backfill_creates_chunks():
    rag = RAGPipeline()
    await rag.startup_backfill()
    
    store = VectorStore()
    stats = await store.get_stats()
    assert stats["total_chunks"] > 0

@pytest.mark.asyncio
@pytest.mark.integration
async def test_backfill_skips_unchanged_files():
    rag = RAGPipeline()
    
    # First backfill
    await rag.startup_backfill()
    stats1 = await store.get_stats()
    
    # Second backfill (no file changes)
    await rag.startup_backfill()
    stats2 = await store.get_stats()
    
    # Total chunks should be same
    assert stats1["total_chunks"] == stats2["total_chunks"]
```

## Performance Targets

- Query embedding (BGE): ~100ms
- Vector search (LanceDB): <50ms
- Result formatting: <10ms
- **Total retrieval latency: <200ms**

- Startup backfill (first run, ~150 chunks): <5 seconds
- Startup backfill (subsequent, no changes): <100ms
- LanceDB→MongoDB sync (10k records): <5 seconds
