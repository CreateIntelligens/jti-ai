import threading

import lancedb
import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class LanceDBStore:
    def __init__(self, uri: str = "data/lancedb", table_name: str = "knowledge"):
        self.uri = uri
        self.table_name = table_name
        self._db = None
        self._table = None
        self._lock = threading.Lock()

    def _ensure_db(self):
        if self._db is None:
            import os
            os.makedirs(self.uri, exist_ok=True)
            self._db = lancedb.connect(self.uri)

    # Columns the current code expects to write. New entries here are auto-added
    # to existing tables on boot, so a code-side schema bump no longer requires
    # manual add_columns() per environment.
    _EXPECTED_STRING_COLUMNS = ("image_id", "url")

    @property
    def table(self):
        """Lazy-loaded LanceDB table with auto-initialization."""
        if self._table is None:
            with self._lock:
                if self._table is None:
                    self._ensure_db()
                    if self.table_name in self._db.list_tables().tables:
                        self._table = self._db.open_table(self.table_name)
                        self._migrate_schema(self._table)
        return self._table

    def _migrate_schema(self, table) -> None:
        existing = {f.name for f in table.schema}
        missing = [c for c in self._EXPECTED_STRING_COLUMNS if c not in existing]
        if not missing:
            return
        try:
            table.add_columns({col: "''" for col in missing})
            logger.info(f"[LanceDB] Migrated schema, added columns: {missing}")
        except Exception as e:
            logger.error(f"[LanceDB] Schema migration failed for columns {missing}: {e}")

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        language: str = "zh",
        source_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if self.table is None:
            return []
        
        # Build filter string
        where_clauses = [f"source_language = '{language}'"]
        if source_type:
            where_clauses.append(f"source_type = '{source_type}'")
        where_str = " AND ".join(where_clauses)
        
        try:
            # Execute search: query_vector should be a 1D array
            query = self.table.search(query_vector)
            if where_str:
                query = query.where(where_str)
            
            results = query.limit(top_k).to_list()
            return results
        except Exception as e:
            logger.error(f"LanceDB search failed: {e}")
            return []

    def insert_chunks(self, chunks: List[Dict[str, Any]]):
        df = pd.DataFrame(chunks)
        with self._lock:
            if self._table is None:
                self._ensure_db()
                if self.table_name in self._db.list_tables().tables:
                    self._table = self._db.open_table(self.table_name)
                else:
                    self._table = self._db.create_table(self.table_name, data=df)
                    return
            self._table.add(df)

    def get_file_fingerprint(self, file_id: str, source_type: str, source_language: str) -> str | None:
        """Returns the stored SHA-256 fingerprint for a file, or None if not indexed."""
        if self.table is None:
            return None
        try:
            where = (
                f"file_id = '{file_id}' "
                f"AND source_type = '{source_type}' "
                f"AND source_language = '{source_language}'"
            )
            rows = self.table.search().where(where).select(["file_fingerprint"]).limit(1).to_list()
            return rows[0]["file_fingerprint"] if rows else None
        except Exception as e:
            logger.warning(f"LanceDB fingerprint check failed: {e}")
            return None

    def delete_by_file(self, file_id: str, source_type: str, source_language: str | None = None):
        if self.table:
            where = f"file_id = '{file_id}' AND source_type = '{source_type}'"
            if source_language:
                where += f" AND source_language = '{source_language}'"
            self.table.delete(where)

    def list_file_ids(self, source_type: str, source_language: str) -> set[str]:
        """All file_ids currently indexed under (source_type, source_language)."""
        if self.table is None:
            return set()
        try:
            where = f"source_type = '{source_type}' AND source_language = '{source_language}'"
            rows = self.table.search().where(where).select(["file_id"]).limit(100000).to_list()
            return {r["file_id"] for r in rows if r.get("file_id")}
        except Exception as e:
            logger.warning(f"LanceDB list_file_ids failed: {e}")
            return set()

    def get_stats(self) -> Dict[str, Any]:
        if self.table:
            return {
                "count": self.table.count_rows(),
                "table_name": self.table_name
            }
        return {"count": 0, "table_name": self.table_name}

_lancedb_store: Optional[LanceDBStore] = None

def get_lancedb_store() -> LanceDBStore:
    global _lancedb_store
    if _lancedb_store is None:
        import os
        uri = os.getenv("LANCEDB_PATH", "data/lancedb")
        table_name = os.getenv("LANCEDB_TABLE_NAME", "knowledge")
        _lancedb_store = LanceDBStore(uri=uri, table_name=table_name)
    return _lancedb_store
