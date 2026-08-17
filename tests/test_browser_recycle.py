"""Unit tests for periodic Playwright browser recycle."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from utils.browser import OptimizedPlaywrightManager


def test_recycles_browser_after_n_execute_calls():
    """After recycle_every completed operations, a full browser restart runs."""

    async def _run():
        mgr = OptimizedPlaywrightManager(
            max_contexts=4, max_concurrent=2, recycle_every=3
        )

        fake_browser = MagicMock()
        fake_browser.new_context = AsyncMock(
            return_value=MagicMock(pages=[], browser=fake_browser)
        )
        fake_browser.close = AsyncMock()

        fake_pw = MagicMock()
        fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_pw.stop = AsyncMock()

        with patch("utils.browser.async_playwright") as ap:
            start_cm = AsyncMock()
            start_cm.start = AsyncMock(return_value=fake_pw)
            ap.return_value = start_cm

            await mgr.start()
            assert mgr._browser_generations == 1
            assert mgr._recycle_count == 0

            async def noop():
                return "ok"

            for _ in range(3):
                assert await mgr.execute_with_semaphore(noop()) == "ok"

            assert mgr._total_requests == 3
            assert mgr._recycle_count == 1
            assert mgr._browser_generations == 2
            assert mgr._requests_since_recycle == 0

            metrics = mgr.get_performance_metrics()
            assert metrics["recycle_every"] == 3
            assert metrics["recycle_count"] == 1
            assert metrics["total_requests"] == 3

            await mgr.close()

    asyncio.run(_run())


def test_recycles_after_n_requests_even_when_busy():
    """Recycle after N completions must not require the worker to be idle.

    Continuous hunter traffic keeps concurrent_operations > 0 forever.
    The Nth completed scrape should start recycle anyway: in-flight work
    finishes on the old browser, new work waits, then Chromium restarts.
    """

    async def _run():
        mgr = OptimizedPlaywrightManager(
            max_contexts=4, max_concurrent=3, recycle_every=2
        )
        fake_browser = MagicMock()
        fake_browser.new_context = AsyncMock(
            return_value=MagicMock(pages=[], browser=fake_browser)
        )
        fake_browser.close = AsyncMock()
        fake_pw = MagicMock()
        fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_pw.stop = AsyncMock()

        with patch("utils.browser.async_playwright") as ap:
            start_cm = AsyncMock()
            start_cm.start = AsyncMock(return_value=fake_pw)
            ap.return_value = start_cm

            await mgr.start()
            hold = asyncio.Event()
            in_flight = asyncio.Event()

            async def blocked():
                in_flight.set()
                await hold.wait()
                return "held"

            async def noop():
                return "ok"

            held_task = asyncio.create_task(mgr.execute_with_semaphore(blocked()))
            await in_flight.wait()
            assert mgr._concurrent_operations == 1

            await mgr.execute_with_semaphore(noop())
            assert mgr._recycle_count == 0
            assert mgr._requests_since_recycle == 1

            # This completion hits the threshold while the held op is
            # still running. Must not skip recycle just because busy.
            trigger = asyncio.create_task(mgr.execute_with_semaphore(noop()))
            for _ in range(50):
                if mgr._recycling or mgr._recycle_count == 1:
                    break
                await asyncio.sleep(0.01)
            assert mgr._recycling or mgr._recycle_count == 1
            assert not held_task.done()

            hold.set()
            assert await held_task == "held"
            assert await trigger == "ok"

            assert mgr._recycle_count == 1
            assert mgr._browser_generations == 2
            assert mgr._requests_since_recycle < mgr._recycle_every
            assert mgr._concurrent_operations == 0

            await mgr.close()

    asyncio.run(_run())


def test_in_flight_get_context_does_not_deadlock_during_recycle():
    """A scrape already counted as in-flight must still obtain a context
    after recycle has started waiting for the drain. Blocking get_context
    on the recycle flag deadlocks (recycle waits for inflight)."""

    async def _run():
        mgr = OptimizedPlaywrightManager(
            max_contexts=4, max_concurrent=3, recycle_every=1
        )
        fake_browser = MagicMock()

        def _new_context(**_kwargs):
            ctx = MagicMock(pages=[], browser=fake_browser)
            ctx.close = AsyncMock()
            return ctx

        fake_browser.new_context = AsyncMock(side_effect=_new_context)
        fake_browser.close = AsyncMock()
        fake_pw = MagicMock()
        fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_pw.stop = AsyncMock()

        with patch("utils.browser.async_playwright") as ap:
            start_cm = AsyncMock()
            start_cm.start = AsyncMock(return_value=fake_pw)
            ap.return_value = start_cm

            await mgr.start()
            entered = asyncio.Event()
            proceed = asyncio.Event()

            async def inflight_then_context():
                entered.set()
                await proceed.wait()
                ctx = await mgr.get_context()
                await mgr.release_context(ctx)
                return "got-context"

            held = asyncio.create_task(
                mgr.execute_with_semaphore(inflight_then_context())
            )
            await entered.wait()

            # Threshold is 1: this completion starts recycle while `held`
            # is still in flight (waiting to call get_context).
            trigger = asyncio.create_task(mgr.execute_with_semaphore(asyncio.sleep(0)))
            for _ in range(50):
                if mgr._recycling:
                    break
                await asyncio.sleep(0.01)
            assert mgr._recycling

            proceed.set()
            assert await asyncio.wait_for(held, timeout=2.0) == "got-context"
            await asyncio.wait_for(trigger, timeout=2.0)
            assert mgr._recycle_count == 1
            await mgr.close()

    asyncio.run(_run())


def test_no_recycle_before_threshold():
    async def _run():
        mgr = OptimizedPlaywrightManager(
            max_contexts=2, max_concurrent=2, recycle_every=10
        )
        fake_browser = MagicMock()
        fake_browser.new_context = AsyncMock(
            return_value=MagicMock(pages=[], browser=fake_browser)
        )
        fake_browser.close = AsyncMock()
        fake_pw = MagicMock()
        fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_pw.stop = AsyncMock()

        with patch("utils.browser.async_playwright") as ap:
            start_cm = AsyncMock()
            start_cm.start = AsyncMock(return_value=fake_pw)
            ap.return_value = start_cm

            await mgr.start()

            async def noop():
                return 1

            for _ in range(9):
                await mgr.execute_with_semaphore(noop())

            assert mgr._recycle_count == 0
            assert mgr._browser_generations == 1
            await mgr.close()

    asyncio.run(_run())
