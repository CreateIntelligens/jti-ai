# Self-Hosted RAG System - Technical Design

## Key Technical Decisions

### 1. Embedding Model: Local BGE (BAAI/bge-m3) via FlagEmbedding

**Decision**: Use BAAI/bge-m3 model loaded locally via FlagEmbedding library (same as openVman).

**Why**:
- No API calls needed (~100ms/query latency, fully local)
- High-quality embeddings (1024 dense dimensions)
- Proven implementation in openVman (battle-tested)
- No rate limits, no API costs, works offline
- FlagEmbedding library handles model loading and batching

**Alternatives Considered**:
- ❌ Gemini text-embedding-004: API dependency, rate limits, slower
- ❌ OpenAI embeddings: Different ecosystem, API costs
- ✅ BGE (FlagEmbedding): Local, free, proven in openVman

**Trade-off**: Requires loading ML model in memory (~2GB), but acceptable for backend service.

### 2. Vector Storage: LanceDB (Primary) + MongoDB (Backup)

**Decision**: LanceDB as primary vector store, MongoDB for backup/persistence.

**Why**:
- **LanceDB**: Native vector DB, ANN search (<10ms), simple Python integration
- **MongoDB**: Existing infrastructure, durability guarantee, disaster recovery
- Hybrid approach gives best of both: speed + reliability
- Mirrors openVman architecture pattern

**Alternatives Considered**:
- ❌ MongoDB alone: No native ANN, Python similarity computation slower
- ❌ LanceDB alone: No persistent backup, single point of failure
- ✅ LanceDB + MongoDB: Fast + durable, proven pattern

**Trade-off**: Two datastores to keep in sync, but manageable with change detection.

### 3. Chunk Storage Strategy: File Fingerprints + Dual Write

**Decision**: Incremental backfill with SHA256 fingerprints; on-update sync to MongoDB backup.

**Why**:
- Avoid re-processing unchanged documents
- Incremental indexing (fast startup)
- MongoDB stays in sync for disaster recovery
- Decouple embedding from chunk creation

**Flow**:
1. Scan source files, compute SHA256 fingerprints
2. Compare with LanceDB state, skip unchanged files
3. For changed files: chunk text → embed with BGE → insert to LanceDB
4. Periodically sync LanceDB records to MongoDB for backup

**LanceDB Schema**:
```python
{
  "text": "...",              # Chunk text
  "vector": [...],           # 1024-dim BGE embedding
  "file_id": "PRP_001",      # Source file ID
  "source_language": "zh",   # "zh" or "en"
  "source_type": "jti_knowledge",  # "jti_knowledge" or "hciot_knowledge"
  "chunk_index": 0,
  "file_fingerprint": "sha256:...",
  "metadata": {...}          # JSON: path, created_at, etc.
}
```

### 4. Two-Layer Architecture Preservation

**Decision**: RAG in first layer (File Search replacement), LLM inference in second layer (unchanged).

**Why**:
- Existing architecture handles persona + session state well
- Only replace retrieval, not inference
- Reduces scope and complexity
- Feature flag enables gradual migration

**First Layer (RAG Pipeline)**:
- Input: query text
- BGE local embedding (~100ms)
- LanceDB search (<10ms)
- Output: `kb_result` + `citations`

**Second Layer (Chat Session)**:
- Input: kb_result + session context
- Output: persona response via Gemini LLM
- Unchanged

### 5. Feature Flag Fallback Strategy

**Decision**: `USE_SELF_RAG=false` (default) → File Search; `true` → LanceDB.

**Why**:
- Zero-downtime migration
- Easy rollback if quality issues
- Parallel A/B testing possible
- Safe canary rollout

**Migration Path**:
1. Deploy with `USE_SELF_RAG=false` (File Search baseline)
2. Run backfill script (LanceDB + MongoDB)
3. Test with `USE_SELF_RAG=true` (internal)
4. Canary: 10% users → LanceDB (monitor metrics)
5. Full rollout: 100% → LanceDB once validated

## Risks & Trade-offs

| Risk | Mitigation |
|------|------------|
| BGE model memory footprint (~2GB) | Acceptable for backend; unload if needed |
| LanceDB + MongoDB sync issues | Change detection via fingerprints; periodic validation |
| Chunk quality affects retrieval | Use semantic chunking (sentence-aware); test with real queries |
| LanceDB data loss (crash) | MongoDB backup enables recovery |
| BGE embedding latency variance | Cache embeddings; monitor p95 latency |

## Migration Plan

### Phase 1: Embedding Service (1 day)
- [ ] Implement EmbeddingService wrapping FlagEmbedding (BGE model)
- [ ] Implement batching and thread-safe encoding
- [ ] Add unit tests for embedding quality

### Phase 2: Vector Storage (1-1.5 days)
- [ ] Implement LanceDB connection and table creation
- [ ] Implement MongoDB backup sync
- [ ] Design incremental backfill with fingerprinting
- [ ] Add vector search with filtering

### Phase 3: RAG Pipeline (1 day)
- [ ] Implement RAGPipeline orchestration (embed → search → format)
- [ ] Add startup backfill
- [ ] Integrate feature flag into routes

### Phase 4: Testing & Validation (1 day)
- [ ] Integration tests (end-to-end RAG flow)
- [ ] Performance tests (latency, throughput)
- [ ] Quality validation (manual spot checks)

### Phase 5: Deployment (0.5 days)
- [ ] Backfill production knowledge base
- [ ] Canary rollout with monitoring
- [ ] Full rollout or rollback decision

## Assumptions

1. Knowledge base documents relatively stable (updates < 1x/day)
2. Corpus size < 500k chunks (typical: 10k-50k)
3. BGE model fits in backend memory (~2GB)
4. LanceDB embedded mode sufficient (no separate process needed)
