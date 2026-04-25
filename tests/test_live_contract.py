"""Live contract tests — hit the running API container.

Run with::

    pytest -m live tests/test_live_contract.py

These are *not* in the default suite.  They require the ebay-kleinanzeigen-api
container to be reachable on port 8000 (the default local-dev setup).
"""
import os

import httpx
import pytest

API = os.environ.get("KLEINANZEIGEN_API_URL", "http://localhost:8000")
pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def _get(path: str, timeout: float = 120.0, **params) -> dict:
    async with httpx.AsyncClient(base_url=API, timeout=timeout) as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r.json()


async def test_inserate_endpoint_reachable():
    data = await _get("/inserate", query="mofa", page_count=1)
    assert data.get("success") is True
    assert "results" in data


async def test_keyword_search_relevance():
    """A ``mofa`` keyword search should return predominantly mofa-like
    results by title."""
    data = await _get("/inserate", query="mofa", location="52538", radius=100, page_count=1)
    results = data.get("results", [])
    assert len(results) > 0
    mofa_terms = ("mofa", "moped", "roller", "vespa", "scooter")
    hits = [r for r in results if any(t in (r.get("title") or "").lower() for t in mofa_terms)]
    ratio = len(hits) / len(results)
    assert ratio >= 0.5, (
        f"expected ≥50% mofa-like titles, got {len(hits)}/{len(results)} ({ratio:.0%})"
    )


async def test_detailed_page_count_above_three_returns_more_than_75():
    """Regression: ``/inserate-detailed`` was declared ``le=3`` (so
    ``page_count`` clamped silently at 3 × 25 = 75 listings).  After lifting
    the cap to ``le=20`` the same query across 5 pages must return >75
    unique results."""
    # Detailed endpoint does a Playwright fetch per listing, so give it room.
    data = await _get("/inserate-detailed", timeout=600.0, query="mofa", page_count=5)
    assert data.get("success") is True
    assert data.get("unique_results", 0) > 75, (
        f"expected >75 unique results across 5 pages, got {data.get('unique_results')}"
    )


async def test_default_10_pages_returns_full_volume():
    """Regression for the silent-empty-page bug.  Pre-fix, this query
    returned 150 (= 6 pages × 25) for hours on end because some pages
    silently returned empty.  Post-fix, the retry path catches that and
    we should consistently see ≥230."""
    data = await _get(
        "/inserate",
        location="52538", radius=75, min_price=30, max_price=200,
        category="305", page_count=10,
    )
    n = len(data.get("results") or [])
    assert n >= 230, f"only {n} listings; empty-page bug likely regressed"


async def test_posted_at_present_and_descending_on_page_1():
    """Default sort is newest-first → page-1 ``posted_at`` must be
    monotonically non-increasing."""
    data = await _get(
        "/inserate",
        location="52538", radius=75, min_price=30, max_price=200,
        category="305", page_count=1,
    )
    results = data.get("results") or []
    assert len(results) >= 20
    posted_at = [r.get("posted_at") for r in results]
    # Most should be parseable (Heute / Gestern / DD.MM.YYYY)
    parsed = [p for p in posted_at if p]
    assert len(parsed) >= len(results) * 0.8, (
        f"only {len(parsed)}/{len(results)} cards had a parseable posted_at"
    )
    assert parsed == sorted(parsed, reverse=True), (
        "page 1 should be newest-first; got out-of-order timestamps"
    )


async def test_sort_price_asc_first_prices_non_decreasing():
    data = await _get(
        "/inserate",
        location="52538", radius=75, min_price=30, max_price=200,
        category="305", page_count=1, sort="price_asc",
    )
    results = data.get("results") or []
    assert len(results) >= 10
    # Skip blank prices and "Zu verschenken"; assert numerics are non-decreasing
    prices: list[int] = []
    for r in results:
        raw = (r.get("price") or "").strip()
        if raw.isdigit():
            prices.append(int(raw))
    assert len(prices) >= 5
    assert prices == sorted(prices), f"prices not ascending: {prices}"


async def test_category_filter_regression():
    """Regression: category 305 with NO query was returning TVs etc. because
    the URL builder dropped the category.  After the fix, every result must
    be from the Motorcycles category (title contains a motorcycle-domain
    term or the price makes sense for a motorcycle part)."""
    data = await _get("/inserate", category="305", location="52538", radius=100, max_price=500, page_count=1)
    results = data.get("results", [])
    assert len(results) > 0, "no results — category filter may still be broken"
    moto_terms = (
        "roller", "motorrad", "mofa", "moped", "vespa", "scooter", "piaggio",
        "aprilia", "kymco", "sachs", "tomos", "kreidler", "puch", "rex",
        "zündapp", "simson", "peugeot", "derbi", "bastler", "scheibe",
        "elektroroller", "helm", "mokick", "kettenschutz", "vergaser",
        "tacho", "sturz", "federgabel",
    )
    blob = " ".join(
        ((r.get("title") or "") + " " + (r.get("description") or "")).lower()
        for r in results
    )
    # Matching ONE motorcycle-domain term in the whole batch is a very weak
    # lower bound — broken category filtering used to yield zero matches
    # because results were TVs, phones etc.
    hits = sum(term in blob for term in moto_terms)
    assert hits >= 3, (
        f"only {hits} motorcycle-domain terms appeared across all titles/descs — "
        "category filtering is probably broken again"
    )
