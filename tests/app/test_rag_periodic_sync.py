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
        patcher = patch.object(app_main, "_list_general_store_names", return_value=["store-a"])
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


if __name__ == "__main__":
    unittest.main()
