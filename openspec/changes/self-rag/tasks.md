# Self-Hosted RAG Implementation Tasks

## Overview

26 implementation tasks organized in 8 phases. Estimated effort: 3-4 days. Uses BGE (FlagEmbedding) + LanceDB (primary) + MongoDB (backup).

## Phase 1: Embedding Service (1 day)

### 1.1 BGE Embedding Service

- [ ] Create `app/services/embedding/__init__.py`
- [ ] Create `app/services/embedding/service.py` with:
  - [ ] `EmbeddingService` class wrapping FlagEmbedding
  - [ ] Load `BAAI/bge-m3` model on first use (lazy loading)
  - [ ] `encode(texts, input_type="document")` method with thread-safe encoding
  - [ ] Batch processing with configurable batch size (default: 32)
  - [ ] Device auto-detection (CUDA if available, else CPU)
- [ ] Create `app/services/embedding/errors.py`:
  - [ ] `EmbeddingError` base class
  - [ ] `EmbeddingModelError` for model loading failures
  - [ ] `EmbeddingEncodingError` for encoding failures
- [ ] Create unit tests:
  - [ ] Test single/batch encoding
  - [ ] Test output shape (N, 1024) and L2-normalization
  - [ ] Test thread-safe concurrent encoding

## Phase 2: Vector Store - LanceDB (1 day)

### 2.1 LanceDB Integration

- [ ] Create `app/services/vector_store/__init__.py`
- [ ] Create `app/services/vector_store/lancedb.py` with:
  - [ ] LanceDB connection initialization
  - [ ] `search(query_embedding, top_k, language, source_type)` method
  - [ ] `insert_chunks(chunks)` method
  - [ ] `delete_by_file(file_id, source_type)` method
  - [ ] `get_stats()` for monitoring
  - [ ] Full-text search index setup
- [ ] Design LanceDB schema (text, vector, file_id, source_language, metadata)
- [ ] Create unit tests:
  - [ ] Test insert and search
  - [ ] Test filtering by language and source_type
  - [ ] Test top-K retrieval

### 2.2 MongoDB Backup Sync

- [ ] Create `app/services/vector_store/mongodb_backup.py` with:
  - [ ] `sync_to_mongodb(lancedb_records)` method
  - [ ] Upsert logic (by file_id + chunk_index)
  - [ ] Batch sync for performance (1000 records/batch)
- [ ] Design MongoDB backup schema (same as LanceDB + sync timestamp)
- [ ] Create MongoDB indexes:
  - [ ] `(file_id, chunk_index)` for upsert key
  - [ ] `(source_language, source_type)` for filtering

## Phase 3: RAG Pipeline (1 day)

### 3.1 RAG Service Core

- [ ] Create `app/services/rag/__init__.py`
- [ ] Create `app/services/rag/service.py` with:
  - [ ] `RAGPipeline` class
  - [ ] `retrieve(query, language, source_type, top_k)` method:
    - [ ] Embed query with BGE (100ms)
    - [ ] Search LanceDB (<50ms)
    - [ ] Format results to `kb_result` + `citations`
    - [ ] Track timing metrics
  - [ ] Error handling with graceful fallback
- [ ] Create `app/services/rag/chunker.py`:
  - [ ] Semantic text chunking (~500 tokens/chunk)
  - [ ] Sentence-aware splitting for quality

### 3.2 Startup Backfill

- [ ] Create `app/services/rag/backfill.py` with:
  - [ ] `startup_backfill()` coroutine
  - [ ] File scanning (JTI + HCIoT knowledge bases)
  - [ ] SHA256 fingerprinting for change detection
  - [ ] Batch embedding with BGE (32 chunks/batch)
  - [ ] LanceDB insertion + MongoDB sync
  - [ ] Logging with progress (files, new chunks, timing)
  - [ ] Error recovery (skip bad files, continue)
- [ ] Integrate into `app/main.py` lifespan
- [ ] Create backfill tests

## Phase 4: Route Integration (0.5 days)

### 4.1 Feature Flag & Route Changes

- [ ] Add `USE_SELF_RAG` environment variable (default: false)
- [ ] Modify `app/routers/jti.py`:
  - [ ] Check feature flag
  - [ ] If true: use RAG pipeline (BGE + LanceDB)
  - [ ] If false: use File Search (existing)
  - [ ] Ensure output format compatibility
- [ ] Test with existing chat flows

## Phase 5: Configuration (0.5 days)

### 5.1 Environment & Dependencies

- [ ] Update `requirements.txt`:
  - [ ] Add `lancedb`
  - [ ] Add `FlagEmbedding`
  - [ ] Add `torch` (optional, for CPU/GPU)
- [ ] Add to `.env.example`:
  - [ ] `USE_SELF_RAG=false`
  - [ ] `EMBEDDING_MODEL=BAAI/bge-m3`
  - [ ] `EMBEDDING_BATCH_SIZE=32`
  - [ ] `EMBEDDING_DEVICE=cuda` (or cpu)
  - [ ] `LANCEDB_PATH=/data/lancedb`
  - [ ] `LANCEDB_TABLE_NAME=knowledge`
  - [ ] `MONGODB_BACKUP_ENABLED=true`
  - [ ] `MONGODB_BACKUP_SYNC_INTERVAL=3600`
  - [ ] `RAG_TOP_K=5`
  - [ ] `RAG_CHUNK_SIZE_TOKENS=500`
  - [ ] `JTI_KNOWLEDGE_PATH=/data/jti_knowledge`
  - [ ] `HCIOT_KNOWLEDGE_PATH=/data/hciot_knowledge`
- [ ] Validate required env vars on startup

## Phase 6: Testing (0.5 days)

### 6.1 Unit Tests

- [ ] Create `tests/services/test_embedding.py`:
  - [ ] Test encode (shape, L2-norm, thread safety)
  - [ ] Coverage: 90%+
- [ ] Create `tests/services/test_vector_store.py`:
  - [ ] Test LanceDB search, insert, delete
  - [ ] Test MongoDB sync
  - [ ] Coverage: 90%+
- [ ] Create `tests/services/test_rag_pipeline.py`:
  - [ ] Test retrieve(), chunking, formatting
  - [ ] Coverage: 85%+

### 6.2 Integration Tests

- [ ] Create `tests/integration/test_rag_e2e.py`:
  - [ ] Backfill fixture data
  - [ ] Query and verify results
  - [ ] Verify latency (<200ms)
- [ ] Create `tests/integration/test_backfill.py`:
  - [ ] Test startup backfill
  - [ ] Test incremental (skip unchanged files)
  - [ ] Test error recovery

## Phase 7: Documentation (0.5 days)

### 7.1 Architecture & Setup Docs

- [ ] Create `docs/rag_architecture.md`:
  - [ ] BGE + LanceDB + MongoDB architecture diagram
  - [ ] Data flow (query → embed → search)
  - [ ] Performance characteristics
- [ ] Create `docs/rag_setup.md`:
  - [ ] Local development setup (LanceDB directory)
  - [ ] Feature flag usage
  - [ ] Monitoring & troubleshooting
- [ ] Add docstrings to all public methods
- [ ] Update README with RAG section

## Phase 8: Deployment & Monitoring (0.5 days)

### 8.1 Monitoring & Health Checks

- [ ] Add logging at critical points:
  - [ ] Embedding latency per batch
  - [ ] Search latency and result count
  - [ ] Backfill progress (files, chunks)
- [ ] Create health check endpoint: `GET /health/rag`
  - [ ] Check LanceDB connection
  - [ ] Check MongoDB backup sync status
  - [ ] Return latency metrics

### 8.2 Deployment Checklist

- [ ] Test with `USE_SELF_RAG=false` (File Search baseline)
- [ ] Run backfill (LanceDB + MongoDB)
  - [ ] Estimate: <5 seconds for 150 chunks
  - [ ] Monitor disk space (LanceDB ~40MB for 10k chunks)
- [ ] Canary: `USE_SELF_RAG=true` for 10% users
  - [ ] Monitor latency (<200ms), error rate (<0.1%)
  - [ ] Manual quality spot check
- [ ] Full rollout: 100% users
- [ ] Keep feature flag for emergency rollback

---

## Dependencies

```
Embedding Service (Phase 1)
    ↓
Vector Store - LanceDB (Phase 2a)
    ↓
Vector Store - MongoDB Backup (Phase 2b)
    ↓
RAG Pipeline (Phase 3)
    ↓
Route Integration (Phase 4)
Config (Phase 5)
Testing (Phase 6)
Documentation (Phase 7)
Deployment (Phase 8)
```

## Success Criteria

- [ ] 80%+ test coverage
- [ ] Query latency: <200ms p95 (100ms embedding + 50ms search + 50ms formatting)
- [ ] Backfill latency: <5 seconds (first run, 150 chunks)
- [ ] Zero regression in quiz/chat flows
- [ ] Feature flag enables safe rollback
- [ ] MongoDB backup stays in sync
- [ ] All documentation complete
