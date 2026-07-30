import asyncio
import logging
import os
from typing import List

from playwright.async_api import async_playwright, BrowserContext, Page

from utils.user_agent import get_random_ua

logger = logging.getLogger(__name__)

# Full Chromium restart after this many scrape operations (env override).
DEFAULT_RECYCLE_EVERY = 10_000


class PlaywrightManager:
    def __init__(self):
        self._playwright = None
        self._browser = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def new_context_page(self):
        context = await self._browser.new_context(user_agent=get_random_ua())
        return await context.new_page()

    async def close_page(self, page):
        await page.close()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


class OptimizedPlaywrightManager:
    """Shared Playwright browser with context pooling and periodic full restart.

    Long-lived Chromium processes degrade (hung navigations, empty pages).
    After ``recycle_every`` scrape operations we close the browser + all
    contexts and launch a fresh one. Recycle waits for in-flight ops so
    callers never hold a closed context mid-request.
    """

    def __init__(
        self,
        max_contexts: int = 10,
        max_concurrent: int = 5,
        recycle_every: int | None = None,
    ):
        self._playwright = None
        self._browser = None
        self._context_pool: List[BrowserContext] = []
        self._context_in_use: List[BrowserContext] = []
        self._max_contexts = max_contexts
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._context_lock = asyncio.Lock()

        if recycle_every is None:
            recycle_every = int(
                os.environ.get("BROWSER_RECYCLE_EVERY", DEFAULT_RECYCLE_EVERY)
            )
        self._recycle_every = max(1, recycle_every)
        self._total_requests = 0
        self._requests_since_recycle = 0
        self._browser_generations = 0
        self._recycle_count = 0
        self._recycling = False
        self._recycle_done = asyncio.Event()
        self._recycle_done.set()
        self._state_lock = asyncio.Lock()

        # Performance metrics
        self._contexts_created = 0
        self._contexts_reused = 0
        self._concurrent_operations = 0
        self._max_concurrent_reached = 0

    async def start(self):
        """Initialize the browser and create initial context pool"""
        await self._launch_browser()

    async def _launch_browser(self):
        """Start Playwright + Chromium and seed the context pool."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._browser_generations += 1

        self._context_pool.clear()
        self._context_in_use.clear()
        self._contexts_created = 0
        self._contexts_reused = 0

        initial_contexts = min(3, self._max_contexts)
        for _ in range(initial_contexts):
            context = await self._browser.new_context(user_agent=get_random_ua())
            self._context_pool.append(context)
            self._contexts_created += 1

        logger.info(
            "Playwright browser started (generation=%d, pool=%d, recycle_every=%d)",
            self._browser_generations,
            len(self._context_pool),
            self._recycle_every,
        )

    async def _shutdown_browser(self):
        """Close all contexts, browser, and playwright driver."""
        for context in list(self._context_pool):
            try:
                await context.close()
            except Exception as exc:
                logger.warning("Error closing pooled context: %s", exc)
        for context in list(self._context_in_use):
            try:
                await context.close()
            except Exception as exc:
                logger.warning("Error closing in-use context: %s", exc)

        self._context_pool.clear()
        self._context_in_use.clear()

        if self._browser:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("Error closing browser: %s", exc)
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("Error stopping playwright: %s", exc)
            self._playwright = None

    async def recycle_browser(self, *, reason: str = "scheduled") -> None:
        """Force a full browser restart once in-flight operations drain.

        Safe to call concurrently; only one recycle runs at a time.
        """
        async with self._state_lock:
            if self._recycling:
                wait_event = self._recycle_done
            else:
                self._recycling = True
                self._recycle_done.clear()
                wait_event = None

        if wait_event is not None:
            await wait_event.wait()
            return

        try:
            # Wait for in-flight scrapes to finish (they still hold contexts).
            while True:
                async with self._state_lock:
                    inflight = self._concurrent_operations
                if inflight <= 0:
                    break
                await asyncio.sleep(0.05)

            async with self._context_lock:
                logger.info(
                    "Recycling Playwright browser (%s) after %d requests "
                    "(lifetime=%d, generation=%d)",
                    reason,
                    self._requests_since_recycle,
                    self._total_requests,
                    self._browser_generations,
                )
                await self._shutdown_browser()
                await self._launch_browser()
                self._requests_since_recycle = 0
                self._recycle_count += 1
                logger.info(
                    "Playwright browser recycled (generation=%d, recycle_count=%d)",
                    self._browser_generations,
                    self._recycle_count,
                )
        finally:
            async with self._state_lock:
                self._recycling = False
                self._recycle_done.set()

    async def _wait_if_recycling(self) -> None:
        while True:
            async with self._state_lock:
                if not self._recycling:
                    return
            await self._recycle_done.wait()

    async def _maybe_schedule_recycle(self) -> None:
        """If the request threshold was hit and nothing is in flight, recycle."""
        async with self._state_lock:
            should = (
                self._requests_since_recycle >= self._recycle_every
                and self._concurrent_operations <= 0
                and not self._recycling
            )
        if should:
            await self.recycle_browser(reason=f"every_{self._recycle_every}_requests")

    async def get_context(self) -> BrowserContext:
        """Get a browser context from the pool or create a new one"""
        await self._wait_if_recycling()
        async with self._context_lock:
            if self._browser is None:
                await self._launch_browser()

            if self._context_pool:
                context = self._context_pool.pop()
                self._context_in_use.append(context)
                self._contexts_reused += 1
                return context

            # Create new context if pool is empty and under limit
            if len(self._context_in_use) < self._max_contexts:
                context = await self._browser.new_context(user_agent=get_random_ua())
                self._context_in_use.append(context)
                self._contexts_created += 1
                return context

            # If we're at the limit, wait and try again
            await asyncio.sleep(0.1)
            return await self.get_context()

    async def release_context(self, context: BrowserContext):
        """Return a context to the pool for reuse"""
        async with self._context_lock:
            if context in self._context_in_use:
                self._context_in_use.remove(context)

                # Close all pages in the context to clean it up
                for page in context.pages:
                    try:
                        await page.close()
                    except Exception:
                        pass

                # Drop contexts during/after recycle; don't re-pool closed ones.
                if self._browser is None or context.browser is None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    return

                # Add back to pool if under limit, otherwise close it
                if len(self._context_pool) < self._max_contexts // 2:
                    self._context_pool.append(context)
                else:
                    await context.close()

    async def execute_with_semaphore(self, coro):
        """Execute a coroutine with concurrency control and request counting."""
        await self._wait_if_recycling()
        async with self._semaphore:
            async with self._state_lock:
                self._concurrent_operations += 1
                self._max_concurrent_reached = max(
                    self._max_concurrent_reached, self._concurrent_operations
                )
            try:
                return await coro
            finally:
                async with self._state_lock:
                    self._concurrent_operations -= 1
                    self._total_requests += 1
                    self._requests_since_recycle += 1
                await self._maybe_schedule_recycle()

    async def new_context_page(self) -> Page:
        """Create a new page using context pooling (backward compatibility)"""
        await self._wait_if_recycling()
        context = await self.get_context()
        page = await context.new_page()
        # Store context reference on page for cleanup
        page._context_ref = context
        return page

    async def close_page(self, page: Page):
        """Close a page and return its context to the pool"""
        context = getattr(page, "_context_ref", None)
        await page.close()
        if context:
            await self.release_context(context)
        # Count legacy page-based path as a request too.
        async with self._state_lock:
            self._total_requests += 1
            self._requests_since_recycle += 1
        await self._maybe_schedule_recycle()

    def get_performance_metrics(self) -> dict:
        """Get current performance metrics"""
        return {
            "contexts_created": self._contexts_created,
            "contexts_reused": self._contexts_reused,
            "contexts_in_pool": len(self._context_pool),
            "contexts_in_use": len(self._context_in_use),
            "max_contexts": self._max_contexts,
            "max_concurrent_reached": self._max_concurrent_reached,
            "current_concurrent": self._concurrent_operations,
            "reuse_ratio": self._contexts_reused / max(self._contexts_created, 1),
            "total_requests": self._total_requests,
            "requests_since_recycle": self._requests_since_recycle,
            "recycle_every": self._recycle_every,
            "browser_generations": self._browser_generations,
            "recycle_count": self._recycle_count,
        }

    async def close(self):
        """Clean up all resources"""
        await self._wait_if_recycling()
        async with self._context_lock:
            await self._shutdown_browser()
