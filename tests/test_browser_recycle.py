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
