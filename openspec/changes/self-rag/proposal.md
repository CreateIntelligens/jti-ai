# Self-Hosted RAG System Proposal

## Why

**Performance**: Gemini File Search has 1-3 second latency per request due to:
- Network round-trip to Gemini API
- File Search infrastructure overhead
- Rate limiting on free tier (20 calls/day)

**Self-hosted alternative**: ~50-100ms latency with:
- Local BGE embedding (BAAI/bge-m3, ~100ms per query, no API calls)
- Vector search in LanceDB (native approximate nearest neighbor, blazing fast)
- Optional MongoDB backup for fault tolerance
- No File Search grounding bugs (system_instruction length causing silent failures)

**Cost**: Free tier constraints eliminated; zero API costs; can scale to production usage.

**Reference**: Follows proven openVman architecture (BGE + LanceDB + optional MongoDB backup).

## What Changes

### 1. Embedding Infrastructure
- Use local BGE model (BAAI/bge-m3) via FlagEmbedding library
- Embeddings generated locally (~100ms/query, no API calls)
- 1024-dimensional dense vectors
- Implement document chunking strategy (semantic chunks from knowledge base)

### 2. Vector Storage & Search
- Primary: LanceDB (native vector DB, ANN search, <10ms searches)
- Backup: MongoDB (for persistence and disaster recovery)
- Pre-filter by document metadata (language, source, file_id)
- Return top K results with relevance scores

### 3. RAG Pipeline
- Query → Embed (local BGE) → Search (LanceDB) → Format → LLM
- Integrate into existing two-layer architecture (chat session layer unchanged)
- Feature flag fallback to File Search during migration

## Impact on Files

| File | Changes |
|------|---------|
| `app/services/embedding/` | New BGE embedding service (local, no API) |
| `app/services/vector_store/` | New LanceDB + MongoDB vector store service |
| `app/services/rag/` | New RAG pipeline orchestration |
| `app/routers/` | Integrate RAG into File Search routes with feature flag |
| `.env.example` | Add LanceDB path, MongoDB backup config |
| `requirements.txt` | Add lancedb, FlagEmbedding |
| `tests/` | New integration tests for embedding, vector search, RAG |
| `scripts/` | New backfill script for LanceDB/MongoDB |

## Success Criteria

- [ ] BGE embeddings generated locally for all knowledge base documents
- [ ] LanceDB vector search returns top-K results in <50ms
- [ ] RAG pipeline latency < 150ms (embedding + search + formatting)
- [ ] MongoDB backup synced with LanceDB (for recovery)
- [ ] Feature flag allows fallback to File Search
- [ ] 80%+ test coverage for new services
- [ ] Zero regression in existing quiz/chat functionality
