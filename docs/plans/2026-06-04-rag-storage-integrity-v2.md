# JTAI RAG Storage Integrity v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deprecate vector_backup in MongoDB completely and unify the RAG storage backfill mechanism so that all files (including general/dynamic stores) are backfilled directly from MongoDB's original files storage. Also resolve the Too Many Open Files (FD) hazard by serializing RAG backfills and setting container ulimits.

**Architecture:** 
1. Expand `BackfillService` to support the `"general"` source type by pulling raw files from `get_knowledge_store()` using `namespace="general"`.
2. Clean up `MongoDBBackup` (vector mirror) sync/restore calls from the entire codebase since RAG chunks can be rebuilt for free from the original files in the DB.
3. Serialize backfill jobs in `app/main.py`'s startup sequence.
4. Set soft/hard `ulimits.nofile` to 65536 in `docker-compose.yml` for the `backend` service.
5. Clean up related CLI scripts and update tests.

**Tech Stack:** Python, FastAPI, MongoDB, LanceDB, Docker Compose, Pytest

---

### Task 1: Add general support and clean up vector backup from BackfillService

**Files:**
- Modify: `app/services/rag/backfill.py`
- Test: `tests/services/test_rag.py`

**Step 1: Write a failing test for general backfill and vector_backup cleanup**

We modify `tests/services/test_rag.py` to remove `mongodb_backup` mock/assertion, and write a new test `test_general_backfill`:

```python
    def test_general_backfill(self):
        backfill = BackfillService()
        mock_gen_store = MagicMock()
        mock_gen_store.list_files.return_value = [
            {"filename": "general_file.txt", "display_name": "General File"}
        ]
        mock_gen_store.get_file_data.return_value = b"general store text data"
        mock_embedding_service.encode.return_value = np.random.rand(1, 1024)
        
        with patch("app.services.rag.backfill.get_knowledge_store", return_value=mock_gen_store):
            backfill.run_backfill("general", "store_123")
            
        mock_lancedb_store.insert_chunks.assert_called_once()
        # Verify it lists files using the store_name (language="store_123") and namespace="general"
        mock_gen_store.list_files.assert_called_once_with("store_123", namespace="general")
        mock_gen_store.get_file_data.assert_called_once_with("store_123", "general_file.txt", namespace="general")
```

Also, modify existing `test_backfill_service` to remove `mock_mongodb_backup` checks since it will be removed.

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_rag.py -k test_general_backfill`
Expected: FAIL due to unsupported source_type or missing `get_knowledge_store` call.

**Step 3: Implement the changes in `app/services/rag/backfill.py`**

- Remove import: `from app.services.vector_store.mongodb_backup import get_mongodb_backup`
- Change `_BACKFILL_SOURCES = ("jti", "hciot", "general")`
- Update `_get_files_and_data`:
```python
        if source_type == "general":
            from app.services.knowledge_store import get_knowledge_store
            store = get_knowledge_store()
            for file_info in store.list_files(language, namespace="general"):
                filename = file_info.get("filename") or file_info.get("name", "")
                if not BackfillService._is_supported_knowledge_file(filename):
                    continue
                data = store.get_file_data(language, filename, namespace="general")
                if data:
                    yield filename, file_info.get("display_name", filename), data, file_info
            return
```
- Remove `self._mongodb_backup` property and variable.
- Remove all sync/delete calls to `mongodb_backup` in `_prune_test_orphans`, `_prune_orphans`, `delete_from_rag`, and `index_single_file`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_rag.py`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/rag/backfill.py tests/services/test_rag.py
git commit -m "feat(rag): support general backfill and remove mongodb backup mirror from backfill"
```

---

### Task 2: Update App lifespan in main.py to serialize backfill execution

**Files:**
- Modify: `app/main.py`
- Test: `tests/services/test_rag.py` (optional startup check)

**Step 2: Implement the changes in `app/main.py`**

Modify `_run_rag_backfill(backfill)` to sequentially process backfills:
```python
async def _run_rag_backfill(backfill):
    """Background task to warm up embedding model and index knowledge files."""
    import time as _time
    loop = asyncio.get_running_loop()
    t0 = _time.time()
    try:
        await loop.run_in_executor(None, backfill.embedding_service.encode, "warmup")
    except Exception as e:
        logger.error("[RAG] Embedding warmup failed: %s", e)
        return

    try:
        # Retrieve all general store names dynamically
        try:
            from app.routers.general.stores import get_store_registry
            registry = get_store_registry()
            query = {
                "$or": [
                    {"managed_app": "general"},
                    {"managed_app": {"$exists": False}},
                    {"managed_app": None},
                ]
            }
            store_docs = registry.collection.find(query, {"name": 1})
            general_store_names = [doc["name"] for doc in store_docs if doc.get("name")]
        except Exception as e:
            logger.error("[RAG] Failed to list general stores: %s", e)
            general_store_names = []

        # Run backfills sequentially to avoid "Too many open files" FD limits
        for src in ["jti", "hciot"]:
            for lang in ["zh", "en"]:
                await loop.run_in_executor(None, backfill.run_backfill, src, lang)

        for store_name in general_store_names:
            await loop.run_in_executor(None, backfill.run_backfill, "general", store_name)

        total = backfill.lancedb_store.get_stats().get("count", 0)
        elapsed = _time.time() - t0
        logger.info("[RAG] Ready — %d chunks indexed in %.1fs", total, elapsed)
    except Exception as e:
        logger.error("[RAG] Backfill failed: %s", e)
```

**Step 3: Run pytest to check lifespan integration**

Run: `pytest`
Expected: PASS

**Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat(rag): sequentially backfill general and system stores on startup to reduce FD pressure"
```

---

### Task 3: Increase ulimits nofile in docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

**Step 2: Implement the changes in `docker-compose.yml`**

Add `ulimits` setting under the `backend` service:
```yaml
    backend:
      build:
        context: .
        dockerfile: docker/backend.Dockerfile
      ulimits:
        nofile:
          soft: 65536
          hard: 65536
```

**Step 3: Verify configuration syntax**

Run: `docker compose config --quiet`
Expected: Success exit code (no output)

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "ops(rag): increase soft and hard nofile ulimits for backend to 65536"
```

---

### Task 4: Clean up other test files and delete retired files

**Files:**
- Modify: `tests/services/test_rag_limits.py`
- Modify: `tests/services/test_vector_store.py`
- Delete: `app/services/vector_store/mongodb_backup.py`
- Delete: `scripts/reconcile_rag.py`

**Step 1: Modify `tests/services/test_rag_limits.py`**

- Remove mock setup for `self._mongodb_backup` and `service.mongodb_backup.list_file_ids.return_value`.
- Update `test_prune_test_orphans` to only expect LanceDB files to be pruned:
```python
    @patch("app.services.rag.backfill.BackfillService.__init__", lambda x: None)
    def test_prune_test_orphans(self):
        service = BackfillService()
        service._lancedb_store = MagicMock()
        service.delete_from_rag = MagicMock()

        service.lancedb_store.list_file_ids.return_value = {"qa_1.txt", "test_2.txt", "QA254-4.txt", "normal_3.txt"}

        service._prune_test_orphans("hciot", "zh")

        self.assertEqual(service.delete_from_rag.call_count, 3)
        called_args = [call[0] for call in service.delete_from_rag.call_args_list]
        called_files = {arg[1] for arg in called_args}
        self.assertEqual(called_files, {"qa_1.txt", "test_2.txt", "QA254-4.txt"})
```

**Step 2: Modify `tests/services/test_vector_store.py`**

- Remove import of `MongoDBBackup`.
- Remove the `test_mongodb_backup_sync` test method.

**Step 3: Delete retired files**

Run:
```bash
rm app/services/vector_store/mongodb_backup.py
rm scripts/reconcile_rag.py
```

**Step 4: Run all tests to verify clean codebase**

Run: `pytest`
Expected: PASS

**Step 5: Commit**

```bash
git rm app/services/vector_store/mongodb_backup.py scripts/reconcile_rag.py
git add tests/services/test_rag_limits.py tests/services/test_vector_store.py
git commit -m "refactor(rag): remove mongodb_backup and reconcile_rag files and update tests"
```
