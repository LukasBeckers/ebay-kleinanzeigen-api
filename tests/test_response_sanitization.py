"""Public responses must not leak ops telemetry or internal exception text."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routers import inserate_ultra
from scrapers.inserate_ultra_optimized import IpBlockedError, UltraOptimizedScraper
from scrapers.seller import get_seller_profile


@pytest.mark.asyncio
async def test_inserate_response_omits_browser_metrics():
    request = MagicMock()
    request.app.state.browser_manager = object()
    scraped = {
        "success": True,
        "results": [{"adid": "1"}],
        "task_metrics": {"x": 1},
        "optimization_features": ["a"],
        "browser_metrics": {
            "max_concurrent": 6,
            "recycle_every": 10000,
            "requests_since_recycle": 3,
        },
        "performance_metrics": {
            "pages_requested": 1,
            "pages_successful": 1,
            "success_rate": 100,
            "average_page_time": 0.5,
            "extra_internal": "drop-me",
        },
    }
    with patch(
        "routers.inserate_ultra.ultra_optimized_scrape_inserate",
        new=AsyncMock(return_value=scraped),
    ):
        body = await inserate_ultra.get_inserate_ultra_optimized(
            request,
            query=None,
            location=None,
            radius=None,
            min_price=None,
            max_price=None,
            page_count=1,
            category=None,
            sort=None,
            attribute_filters=None,
        )

    assert "browser_metrics" not in body
    assert "task_metrics" not in body
    assert body["performance_metrics"] == {
        "pages_requested": 1,
        "pages_successful": 1,
        "success_rate": 100,
        "average_page_time": 0.5,
    }


@pytest.mark.asyncio
async def test_ip_block_client_detail_omits_scrape_url():
    browser_manager = MagicMock()
    browser_manager.max_concurrent = 1

    async def boom(coro):
        coro.close()
        raise IpBlockedError(
            "page 1 Kleinanzeigen IP block (http 403): "
            "https://www.kleinanzeigen.de/s-secret-query/k0"
        )

    browser_manager.execute_with_semaphore = AsyncMock(side_effect=boom)
    scraper = UltraOptimizedScraper(browser_manager)
    with pytest.raises(HTTPException) as caught:
        await scraper.ultra_optimized_fetch_page(
            "https://www.kleinanzeigen.de/s-secret-query/k0",
            page_num=1,
            retry_count=0,
        )
    assert caught.value.status_code == 403
    assert caught.value.detail == "upstream blocked"
    assert "kleinanzeigen.de" not in str(caught.value.detail)
    assert "secret-query" not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_seller_failure_detail_omits_exception_text():
    manager = MagicMock()

    async def boom(coro):
        coro.close()
        raise RuntimeError("playwright crashed at /tmp/secret-path")

    manager.execute_with_semaphore = AsyncMock(side_effect=boom)
    with pytest.raises(HTTPException) as caught:
        await get_seller_profile(manager, "12345", retry_count=0)
    assert caught.value.status_code == 500
    assert caught.value.detail == "Failed to fetch seller"
    assert "secret-path" not in str(caught.value.detail)
    assert "playwright" not in str(caught.value.detail).lower()


@pytest.mark.asyncio
async def test_inserat_parse_failure_detail_omits_exception_text():
    from scrapers.inserat import get_inserate_details

    class _BrokenPage:
        url = "https://www.kleinanzeigen.de/s-anzeige/secret-listing"

        async def goto(self, *_args, **_kwargs):
            raise RuntimeError("playwright crashed at /tmp/secret-inserat-path")

    with pytest.raises(HTTPException) as caught:
        await get_inserate_details(
            "https://www.kleinanzeigen.de/s-anzeige/secret-listing",
            _BrokenPage(),
        )
    assert caught.value.status_code == 500
    assert caught.value.detail == "Failed to fetch listing details"
    assert "secret-inserat-path" not in str(caught.value.detail)
    assert "playwright" not in str(caught.value.detail).lower()


@pytest.mark.asyncio
async def test_inserat_retry_fallback_detail_omits_structured_message():
    from scrapers.inserat import get_inserate_details_optimized

    browser_manager = MagicMock()
    browser_manager.get_performance_metrics.side_effect = RuntimeError(
        "metrics blew up with /tmp/secret-metrics-path"
    )

    async def boom(coro):
        coro.close()
        raise RuntimeError("playwright crashed at /tmp/secret-retry-path")

    browser_manager.execute_with_semaphore = AsyncMock(side_effect=boom)
    with pytest.raises(HTTPException) as caught:
        await get_inserate_details_optimized(
            browser_manager, "2674165671", retry_count=0
        )
    assert caught.value.status_code == 500
    detail = caught.value.detail
    text = detail if isinstance(detail, str) else str(detail)
    assert "Failed to fetch listing details" in text
    assert "secret-retry-path" not in text
    assert "secret-metrics-path" not in text
    assert "playwright" not in text.lower()
