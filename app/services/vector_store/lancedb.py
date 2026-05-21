import threading
import os

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

    def _get_db(self):
        """Lazy-connect to the database."""
        if self._db is None:
            if not self.uri.startswith("memory://"):
                os.makedirs(self.uri, exist_ok=True)
            self._db = lancedb.connect(self.uri)
        return self._db

    _EXPECTED_STRING_COLUMNS = ("image_id", "url")

    @property
    def table(self):
        """Lazy-loaded LanceDB table with auto-initialization and migration."""
        if self._table is not None:
            return self._table

        with self._lock:
            if self._table is None:
                db = self._get_db()
                if self.table_name in db.list_tables().tables:
                    table = db.open_table(self.table_name)
                    self._migrate_schema(table)
                    self._table = table
        return self._table

    def _migrate_schema(self, table) -> None:
        """Adds missing columns to the existing table schema."""
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
        source_type: Optional[str | List[str]] = None
    ) -> List[Dict[str, Any]]:
        tbl = self.table
        if tbl is None:
            return []

        where = f"source_language = '{language}'"
        if source_type:
            if isinstance(source_type, (list, tuple, set)):
                source_types_str = ", ".join(f"'{st}'" for st in source_type)
                where += f" AND source_type IN ({source_types_str})"
            else:
                where += f" AND source_type = '{source_type}'"

        try:
            return tbl.search(query_vector).where(where).limit(top_k).to_list()
        except Exception as e:
            logger.error(f"LanceDB search failed: {e}")
            return []

    def insert_chunks(self, chunks: List[Dict[str, Any]]):
        """Inserts data chunks into the table, creating it if it doesn't exist."""
        df = pd.DataFrame(chunks)

        table = self.table
        if table is not None:
            table.add(df)
            return

        with self._lock:
            # Re-check inside lock; if still None, create it
            if self._table is None:
                db = self._get_db()
                if self.table_name in db.list_tables().tables:
                    self._table = db.open_table(self.table_name)
                    self._migrate_schema(self._table)
                else:
                    self._table = db.create_table(self.table_name, data=df)
                    return

            self._table.add(df)

    def get_file_fingerprint(self, file_id: str, source_type: str, source_language: str) -> str | None:
        """Returns the stored SHA-256 fingerprint for a file, or None if not indexed."""
        tbl = self.table
        if tbl is None:
            return None
        try:
            where = f"file_id = '{file_id}' AND source_type = '{source_type}' AND source_language = '{source_language}'"
            rows = tbl.search().where(where).select(["file_fingerprint"]).limit(1).to_list()
            return rows[0]["file_fingerprint"] if rows else None
        except Exception as e:
            logger.warning(f"LanceDB fingerprint check failed: {e}")
            return None

    def delete_by_file(self, file_id: str, source_type: str, source_language: str | None = None):
        """Deletes all entries associated with a specific file."""
        tbl = self.table
        if tbl is None:
            return

        where = f"file_id = '{file_id}' AND source_type = '{source_type}'"
        if source_language:
            where += f" AND source_language = '{source_language}'"
        tbl.delete(where)

    def list_file_ids(self, source_type: str, source_language: str) -> set[str]:
        """Returns a set of all file_ids indexed for the given type and language."""
        tbl = self.table
        if tbl is None:
            return set()
        try:
            where = f"source_type = '{source_type}' AND source_language = '{source_language}'"
            rows = tbl.search().where(where).select(["file_id"]).limit(100000).to_list()
            return {r["file_id"] for r in rows if r.get("file_id")}
        except Exception as e:
            logger.warning(f"LanceDB list_file_ids failed: {e}")
            return set()

    def get_stats(self) -> Dict[str, Any]:
        """Returns basic statistics about the table."""
        tbl = self.table
        count = tbl.count_rows() if tbl else 0
        return {"count": count, "table_name": self.table_name}

_lancedb_store: Optional[LanceDBStore] = None

def get_lancedb_store() -> LanceDBStore:
    global _lancedb_store
    if _lancedb_store is None:
        _lancedb_store = LanceDBStore(
            uri=os.getenv("LANCEDB_PATH", "data/lancedb"),
            table_name=os.getenv("LANCEDB_TABLE_NAME", "knowledge"),
        )
    return _lancedb_store
