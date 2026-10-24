"""An IP block must leave /inserate as HTTP 403.

The page batch used to keep going after ``HTTPException(403)``. The route
then answered 200 with ``success: false`` and no error, so the proxy counted
the worker as healthy and Listing Hunter only saw "upstream search failed".
A real empty results page stays HTTP 200 with ``success: true``.
"""
import asyncio
import time

from fastapi import HTTPException

from scrapers.inserate_ultra_optimized import UltraOptimizedScraper
from utils.browser import OptimizedPlaywrightManager
from utils.performance import PageMetrics


def _scraper() -> UltraOptimizedScraper:
    manager = OptimizedPlaywrightManager(
        max_contexts=2, max_concurrent=2, recycle_every=1000
    )
    return UltraOptimizedScraper(manager)


def test_ip_block_is_not_returned_as_an_empty_success():
    async def _run():
        scraper = _scraper()

        async def _blocked(url, page_num, retry_count=2):
            raise HTTPException(
                status_code=403,
                detail=f"page {page_num} Kleinanzeigen IP block (http 403): {url}",
            )

        scraper.ultra_optimized_fetch_page = _blocked
        try:
            await scraper.ultra_optimized_scrape(query="fahrrad", page_count=1)
        except HTTPException as exc:
            assert exc.status_code == 403
            assert "IP block" in str(exc.detail)
            return
        raise AssertionError("IP block was swallowed as a normal search response")

    asyncio.run(_run())


def test_empty_results_page_stays_a_successful_search():
    async def _run():
        scraper = _scraper()

        async def _empty(url, page_num, retry_count=2):
            now = time.time()
            metrics = PageMetrics(
                page_number=page_num,
                url=url,
                start_time=now,
                end_time=now,
                success=True,
                retry_count=0,
                results_count=0,
            )
            return [], metrics

        scraper.ultra_optimized_fetch_page = _empty
        response = await scraper.ultra_optimized_scrape(query="fahrrad", page_count=1)
        assert response["success"] is True
        assert response["results"] == []

    asyncio.run(_run())
