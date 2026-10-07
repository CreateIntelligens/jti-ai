"""Index audit：每台機器的 LanceDB 都要與共用 Mongo 一致，部署後靠它驗證。"""
import unittest
from unittest.mock import MagicMock, patch

from app.services.rag import index_audit


def _row(source_type, lang, file_id, idx, fp):
    return {
        "source_type": source_type,
        "source_language": lang,
        "file_id": file_id,
        "chunk_index": idx,
        "file_fingerprint": fp,
    }


class TestRagIndexAudit(unittest.TestCase):
    def _audit(self, rows, live_files, table_name="knowledge_embeddinggemma_2_768", dims=768):
        backfill = MagicMock()
        store = backfill.lancedb_store
        store.table_name = table_name
        store._get_db.return_value.list_tables.return_value.tables = [table_name, "knowledge"]
        store.table.schema.field.return_value.type.list_size = dims
        store.table.search.return_value.select.return_value.limit.return_value.to_list.return_value = rows
        backfill._get_files_and_data.side_effect = lambda st, part: [
            (name, name, data, {}) for name, data in live_files.get((st, part), {}).items()
        ]
        backfill._extract_file_text.side_effect = lambda name, data: data.decode()
        backfill._compute_fingerprint.side_effect = lambda data: "fp-" + data.decode()

        with (
            patch.object(index_audit, "get_backfill_service", return_value=backfill),
            patch.object(index_audit, "knowledge_table_name", return_value="knowledge_embeddinggemma_2_768"),
            patch.object(index_audit, "configured_dimensions", return_value=768),
        ):
            return index_audit.audit_rag_index([("jti", "zh"), ("general", "store_a")])

    def test_matching_index_is_clean(self):
        report = self._audit(
            rows=[
                _row("jti_knowledge", "zh", "a.csv", 0, "fp-A"),
                _row("general_knowledge", "store_a", "g.csv", 0, "fp-G"),
            ],
            live_files={("jti", "zh"): {"a.csv": b"A"}, ("general", "store_a"): {"g.csv": b"G"}},
        )
        self.assertTrue(report["clean"])
        self.assertEqual(report["other_tables"], ["knowledge"])

    def test_detects_missing_stale_orphan_and_deleted_store(self):
        report = self._audit(
            rows=[
                _row("jti_knowledge", "zh", "a.csv", 0, "fp-OLD"),      # 內容已改
                _row("jti_knowledge", "zh", "gone.csv", 0, "fp-X"),     # 檔案已刪
                _row("general_knowledge", "store_deleted", "x.csv", 0, "fp-X"),  # store 已刪
            ],
            live_files={
                ("jti", "zh"): {"a.csv": b"A", "new.csv": b"N", "empty.csv": b""},
                ("general", "store_a"): {},
            },
        )
        part = report["partitions"]["jti_knowledge/zh"]
        self.assertFalse(report["clean"])
        self.assertEqual(part["stale"], ["a.csv"])
        self.assertEqual(part["orphans"], ["gone.csv"])
        # 抽不出文字的檔案本來就不會被索引，不算缺漏
        self.assertEqual(part["missing"], ["new.csv"])
        self.assertEqual(report["orphan_partitions"], {"general_knowledge/store_deleted": 1})

    def test_duplicate_chunks_are_not_clean(self):
        row = _row("jti_knowledge", "zh", "a.csv", 0, "fp-A")
        report = self._audit(rows=[row, dict(row)], live_files={("jti", "zh"): {"a.csv": b"A"}})
        self.assertEqual(report["duplicate_chunks"], 1)
        self.assertFalse(report["clean"])

    def test_wrong_model_table_is_not_clean(self):
        report = self._audit(rows=[], live_files={}, table_name="knowledge", dims=1024)
        self.assertFalse(report["clean"])


if __name__ == "__main__":
    unittest.main()
