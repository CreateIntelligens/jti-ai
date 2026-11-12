"""Periodic incremental RAG sync.

Each host keeps its own LanceDB but shares MongoDB with the other hosts. A
knowledge edit made through one host's admin API only indexes that host, so
the other host kept answering from stale vectors until it restarted.
"""
import importlib
import unittest
from unittest.mock import MagicMock, patch

from tests.support.app_test_support import get_test_app

get_test_app()
app_main = importlib.import_module("app.main")


class TestRagSyncInterval(unittest.TestCase):
    def test_defaults_to_five_minutes(self):
        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("RAG_SYNC_INTERVAL_SECONDS", None)
            self.assertEqual(app_main._rag_sync_interval_seconds(), 300)

    def test_zero_disables(self):
        with patch.dict("os.environ", {"RAG_SYNC_INTERVAL_SECONDS": "0"}):
            self.assertEqual(app_main._rag_sync_interval_seconds(), 0)

    def test_invalid_value_falls_back_to_default(self):
        with patch.dict("os.environ", {"RAG_SYNC_INTERVAL_SECONDS": "soon"}):
            self.assertEqual(app_main._rag_sync_interval_seconds(), 300)


class TestRagSyncRound(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.backfill = MagicMock()
        for name, value in (
            ("_list_general_store_names", ["store-a"]),
            ("_list_all_store_names", {"store-a", "store-key-mapped"}),
        ):
            patcher = patch.object(app_main, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # 測試環境連不到主庫時，app 啟動會把自己標成 fallback，清理就會被跳過。
        patcher = patch("app.services.mongo_client.is_using_fallback", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_runs_incremental_backfill_for_every_job_and_releases_lock(self):
        with (
            patch.object(app_main, "_acquire_backfill_lock", return_value="tok"),
            patch.object(app_main, "_release_backfill_lock") as release,
        ):
            ran = await app_main._run_rag_sync_round(self.backfill, self.client)

        self.assertTrue(ran)
        called_jobs = [c.args for c in self.backfill.run_backfill.call_args_list]
        self.assertEqual(
            called_jobs,
            [*app_main._FIXED_RAG_BACKFILL_JOBS, ("general", "store-a")],
        )
        release.assert_called_once_with(self.client, "tok")

    async def test_skips_round_while_another_worker_is_indexing(self):
        with (
            patch.object(app_main, "_acquire_backfill_lock", return_value=None),
            patch.object(app_main, "_release_backfill_lock") as release,
        ):
            ran = await app_main._run_rag_sync_round(self.backfill, self.client)

        self.assertFalse(ran)
        self.backfill.run_backfill.assert_not_called()
        release.assert_not_called()

    async def test_failure_still_releases_lock(self):
        self.backfill.run_backfill.side_effect = RuntimeError("mongo down")
        with (
            patch.object(app_main, "_acquire_backfill_lock", return_value="tok"),
            patch.object(app_main, "_release_backfill_lock") as release,
        ):
            await app_main._run_rag_sync_round(self.backfill, self.client)

        release.assert_called_once_with(self.client, "tok")

    async def test_runs_without_redis(self):
        ran = await app_main._run_rag_sync_round(self.backfill, None)

        self.assertTrue(ran)
        self.assertEqual(
            self.backfill.run_backfill.call_count,
            len(app_main._FIXED_RAG_BACKFILL_JOBS) + 1,
        )

    async def test_prunes_against_every_store_not_just_general_app(self):
        await app_main._run_rag_sync_round(self.backfill, None)

        self.backfill.prune_deleted_general_stores.assert_called_once_with({"store-a", "store-key-mapped"})


class TestPruneDeletedGeneralStores(unittest.TestCase):
    def test_skips_on_fallback_database(self):
        backfill = MagicMock()
        with (
            patch("app.services.mongo_client.is_using_fallback", return_value=True),
            patch.object(app_main, "_list_all_store_names", return_value={"store-a"}) as list_all,
        ):
            app_main._prune_deleted_general_stores(backfill)

        list_all.assert_not_called()
        backfill.prune_deleted_general_stores.assert_not_called()

    def test_skips_when_store_list_unreadable(self):
        backfill = MagicMock()
        with (
            patch("app.services.mongo_client.is_using_fallback", return_value=False),
            patch.object(app_main, "_list_all_store_names", return_value=None),
        ):
            app_main._prune_deleted_general_stores(backfill)

        backfill.prune_deleted_general_stores.assert_not_called()

    def test_all_store_names_ignore_app_and_owner(self):
        # 綁在 jti key 下的店、個人 key 的店也把向量放在 general_knowledge，
        # 它們必須算「還存在」，否則每輪同步都會被清掉。
        registry = MagicMock()
        registry.collection.find.return_value = [
            {"name": "store_general"},
            {"name": "store_jti_key", "managed_app": "jti"},
            {"name": "store_byok", "owner_key_hash": "abc"},
        ]
        with patch("app.routers.general.stores.get_store_registry", return_value=registry):
            names = app_main._list_all_store_names()

        self.assertEqual(names, {"store_general", "store_jti_key", "store_byok"})
        registry.collection.find.assert_called_once_with({}, {"name": 1})
        registry.list_stores.assert_not_called()

    def test_all_store_names_report_outage_as_none(self):
        registry = MagicMock()
        registry.collection.find.side_effect = RuntimeError("mongo down")
        with patch("app.routers.general.stores.get_store_registry", return_value=registry):
            self.assertIsNone(app_main._list_all_store_names())


if __name__ == "__main__":
    unittest.main()
