"""Search scheduling must keep the configured concurrency when the browser is busy."""
import asyncio

from scrapers.inserate_ultra_optimized import UltraOptimizedScraper
from utils.browser import OptimizedPlaywrightManager


def test_busy_browser_does_not_build_a_zero_task_semaphore():
    """Free-slot count is 0 while scrapes run. The task limit stays at 3."""

    async def _run():
        mgr = OptimizedPlaywrightManager(
            max_contexts=4, max_concurrent=3, recycle_every=1000
        )
        for _ in range(3):
            await mgr._semaphore.acquire()
        assert mgr._semaphore._value == 0

        scraper = UltraOptimizedScraper(mgr)
        assert scraper.task_manager.semaphore._value == 3
        assert scraper.memory_processor.semaphore._value == 3

        async def _ok():
            return "ok"

        result = await asyncio.wait_for(
            scraper.task_manager.gather_with_limit([_ok()]),
            timeout=1.0,
        )
        assert result == ["ok"]

    asyncio.run(_run())


def test_max_concurrent_below_one_is_rejected():
    try:
        OptimizedPlaywrightManager(max_concurrent=0)
    except ValueError as exc:
        assert "max_concurrent" in str(exc)
    else:
        raise AssertionError("max_concurrent=0 should be rejected")
