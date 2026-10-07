import asyncio
import importlib
import time
import unittest
from unittest.mock import MagicMock, patch

from tests.support.app_test_support import get_test_app

app = get_test_app()
app_main = importlib.import_module("app.main")


class TestAppLifespan(unittest.TestCase):
    def test_app_uses_lifespan_instead_of_on_startup_handlers(self):
        self.assertEqual(app.router.on_startup, [])


class TestBackfillLock(unittest.TestCase):
    """多 worker 下只有一個 process 能跑啟動 backfill，否則會寫出重複 chunk。"""

    def test_winner_acquires_lock_with_nx(self):
        client = MagicMock()
        client.set.return_value = True

        token = app_main._acquire_backfill_lock(client)

        self.assertTrue(token)
        self.assertTrue(client.set.call_args.kwargs["nx"])
        # 寫入的 value 必須就是回傳的 token，否則釋放時比對不到。
        self.assertEqual(client.set.call_args.args[1], token)

    def test_each_acquire_uses_a_distinct_token(self):
        client = MagicMock()
        client.set.return_value = True

        first = app_main._acquire_backfill_lock(client)
        second = app_main._acquire_backfill_lock(client)

        self.assertNotEqual(first, second)

    def test_loser_does_not_acquire_lock(self):
        client = MagicMock()
        client.set.return_value = None

        self.assertIsNone(app_main._acquire_backfill_lock(client))

    def test_redis_failure_still_indexes(self):
        """Redis 掛掉時寧可重複索引，也不能整個跳過不索引。"""
        client = MagicMock()
        client.set.side_effect = RuntimeError("redis down")

        token = app_main._acquire_backfill_lock(client)

        # 哨兵值不是 None（None 代表輸給別的 worker，會跳過索引）。
        self.assertIsNotNone(token)
        self.assertEqual(token, app_main._RAG_BACKFILL_LOCK_UNHELD_TOKEN)

    def test_held_lock_keeps_renewing_until_released(self):
        """短 TTL 靠心跳續約：活著的持有者不會在長時間 backfill 中途掉鎖。"""
        client = MagicMock()
        client.set.return_value = True
        client.eval.return_value = 1

        with patch.object(app_main, "_RAG_BACKFILL_LOCK_RENEW_SECONDS", 0.01):
            token = app_main._acquire_backfill_lock(client)
            time.sleep(0.1)
            app_main._release_backfill_lock(client, token)
            renewals = [
                c for c in client.eval.call_args_list
                if c.args[0] == app_main._RENEW_LOCK_IF_OWNED
            ]
            self.assertGreaterEqual(len(renewals), 2)
            self.assertEqual(renewals[0].args[3], token)
            self.assertEqual(
                renewals[0].args[4], app_main._RAG_BACKFILL_LOCK_TTL_SECONDS
            )
            count_after_release = client.eval.call_count
            time.sleep(0.1)

        self.assertEqual(client.eval.call_count, count_after_release)
        self.assertNotIn(token, app_main._backfill_lock_renewals)

    def test_renewal_stops_once_lock_is_lost(self):
        client = MagicMock()
        client.set.return_value = True
        client.eval.return_value = 0  # 鎖已不是自己的

        with patch.object(app_main, "_RAG_BACKFILL_LOCK_RENEW_SECONDS", 0.01):
            token = app_main._acquire_backfill_lock(client)
            time.sleep(0.1)

        self.assertEqual(client.eval.call_count, 1)
        app_main._release_backfill_lock(client, token)

    def test_lock_ttl_is_short_enough_for_a_killed_holder(self):
        """持有者被 SIGKILL 時沒人釋放；TTL 決定新容器最多要等多久。"""
        client = MagicMock()
        client.set.return_value = True

        token = app_main._acquire_backfill_lock(client)
        app_main._release_backfill_lock(client, token)

        self.assertLessEqual(client.set.call_args.kwargs["ex"], 120)
        self.assertLess(
            app_main._RAG_BACKFILL_LOCK_RENEW_SECONDS,
            app_main._RAG_BACKFILL_LOCK_TTL_SECONDS / 2,
        )

    def test_release_only_deletes_when_token_matches(self):
        """TTL 過期換手後，舊 worker 不能刪掉新持有者的鎖。"""
        client = MagicMock()

        app_main._release_backfill_lock(client, "my-token")

        client.delete.assert_not_called()
        args = client.eval.call_args.args
        self.assertEqual(args[2], app_main._RAG_BACKFILL_LOCK_KEY)
        self.assertEqual(args[3], "my-token")

    def test_release_is_a_noop_when_lock_was_never_held(self):
        client = MagicMock()

        app_main._release_backfill_lock(
            client, app_main._RAG_BACKFILL_LOCK_UNHELD_TOKEN
        )

        client.eval.assert_not_called()
        client.delete.assert_not_called()

    def test_release_survives_redis_failure(self):
        client = MagicMock()
        client.eval.side_effect = RuntimeError("redis down")

        app_main._release_backfill_lock(client, "my-token")

    def test_wait_reports_observed_lock_release(self):
        client = MagicMock()
        client.exists.return_value = False

        self.assertTrue(app_main._wait_for_backfill_lock_release(client))

    def test_wait_reports_poll_failure(self):
        client = MagicMock()
        client.exists.side_effect = RuntimeError("redis down")

        self.assertFalse(app_main._wait_for_backfill_lock_release(client))


class TestBackfillCoordination(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.backfill = MagicMock()
        self.backfill.lancedb_store.get_stats.return_value = {"count": 0}

    async def test_waiter_reacquires_and_runs_incremental_backfill(self):
        """鎖釋放不代表前一個 worker 成功，等待者必須接手補跑。"""
        with (
            patch.object(
                app_main,
                "_acquire_backfill_lock",
                side_effect=[None, "retry-token"],
            ) as acquire,
            patch.object(
                app_main,
                "_build_backfill_lock_client",
                return_value=self.client,
            ),
            patch.object(
                app_main,
                "_release_backfill_lock",
            ) as release,
            patch.object(
                app_main,
                "_wait_for_backfill_lock_release",
                return_value=True,
            ) as wait,
        ):
            await app_main._run_rag_backfill(self.backfill)

        self.assertEqual(acquire.call_count, 2)
        wait.assert_called_once_with(self.client)
        self.assertEqual(
            self.backfill.run_backfill.call_count,
            len(app_main._FIXED_RAG_BACKFILL_JOBS),
        )
        release.assert_called_once_with(self.client, "retry-token")

    async def test_poll_failure_fails_open_when_redis_is_unavailable(self):
        with (
            patch.object(
                app_main,
                "_acquire_backfill_lock",
                side_effect=[
                    None,
                    app_main._RAG_BACKFILL_LOCK_UNHELD_TOKEN,
                ],
            ),
            patch.object(
                app_main,
                "_build_backfill_lock_client",
                return_value=self.client,
            ),
            patch.object(
                app_main,
                "_release_backfill_lock",
            ) as release,
            patch.object(
                app_main,
                "_wait_for_backfill_lock_release",
                return_value=False,
            ),
        ):
            await app_main._run_rag_backfill(self.backfill)

        self.assertEqual(
            self.backfill.run_backfill.call_count,
            len(app_main._FIXED_RAG_BACKFILL_JOBS),
        )
        release.assert_called_once_with(
            self.client,
            app_main._RAG_BACKFILL_LOCK_UNHELD_TOKEN,
        )

    async def test_still_held_lock_does_not_report_ready_or_run_backfill(self):
        with (
            patch.object(
                app_main,
                "_acquire_backfill_lock",
                side_effect=[None, None],
            ),
            patch.object(
                app_main,
                "_build_backfill_lock_client",
                return_value=self.client,
            ),
            patch.object(
                app_main,
                "_wait_for_backfill_lock_release",
                return_value=False,
            ),
            self.assertLogs(app_main.logger, level="WARNING") as logs,
        ):
            await app_main._run_rag_backfill(self.backfill)

        self.backfill.run_backfill.assert_not_called()
        self.assertIn("startup backfill deferred", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()


class TestEmbeddingWarmup(unittest.IsolatedAsyncioTestCase):
    """embedding 跟 backend 一起重開時模型還在下載；暖機要等，不能直接放棄索引。"""

    async def test_retries_until_embedding_is_ready(self):
        backfill = MagicMock()
        backfill.embedding_service.encode.side_effect = [
            RuntimeError("model loading"),
            RuntimeError("model loading"),
            [[0.0]],
        ]
        loop = asyncio.get_running_loop()
        with patch.object(app_main, "_RAG_WARMUP_RETRY_SECONDS", 0):
            ready = await app_main._wait_for_embedding(backfill, loop)

        self.assertTrue(ready)
        self.assertEqual(backfill.embedding_service.encode.call_count, 3)

    async def test_gives_up_after_timeout(self):
        backfill = MagicMock()
        backfill.embedding_service.encode.side_effect = RuntimeError("down")
        loop = asyncio.get_running_loop()
        with (
            patch.object(app_main, "_RAG_WARMUP_RETRY_SECONDS", 0),
            patch.object(app_main, "_RAG_WARMUP_TIMEOUT_SECONDS", 0),
        ):
            ready = await app_main._wait_for_embedding(backfill, loop)

        self.assertFalse(ready)

