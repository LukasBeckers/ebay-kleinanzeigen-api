"""Playwright scrape of a Kleinanzeigen seller profile / shop page."""

from __future__ import annotations

import time

from fastapi import HTTPException

from libs.websites.seller import (
    PROFILE_URL,
    parse_seller_profile,
    parse_seller_shop,
)
from utils.browser import OptimizedPlaywrightManager


def _merge_shop(profile: dict, shop: dict) -> dict:
    """Fill blanks on the profile payload from a /pro/ shop page."""
    out = dict(profile)
    for key in (
        "name",
        "since",
        "shop_url",
        "followers",
        "ads_online",
        "ads_total",
        "id",
    ):
        if out.get(key) in (None, "", []) and shop.get(key) not in (None, "", []):
            out[key] = shop[key]
    if shop.get("badges"):
        seen = set(out.get("badges") or [])
        badges = list(out.get("badges") or [])
        for b in shop["badges"]:
            if b not in seen:
                badges.append(b)
                seen.add(b)
        out["badges"] = badges
    if shop.get("type") == "business":
        out["type"] = "business"
    return out


async def get_seller_profile(
    browser_manager: OptimizedPlaywrightManager,
    user_id: str,
    retry_count: int = 2,
) -> dict:
    url = PROFILE_URL.format(user_id=user_id)
    last_error: Exception | None = None

    for attempt in range(retry_count + 1):
        start = time.time()
        context = None
        page = None
        try:

            async def fetch_operation():
                nonlocal context, page
                context = await browser_manager.get_context()
                page = await context.new_page()
                await page.goto(url, timeout=120000)
                html = await page.content()
                seller = parse_seller_profile(html, user_id=user_id)
                shop_url = seller.get("shop_url")
                if shop_url and seller.get("ads_online") is None:
                    await page.goto(shop_url, timeout=120000)
                    shop = parse_seller_shop(await page.content(), user_id=user_id)
                    seller = _merge_shop(seller, shop)
                return seller

            seller = await browser_manager.execute_with_semaphore(fetch_operation())
            if not seller.get("id") and not seller.get("name"):
                raise HTTPException(
                    status_code=404, detail=f"Seller {user_id} not found"
                )
            return {
                "success": True,
                "data": seller,
                "time_taken": round(time.time() - start, 3),
            }
        except HTTPException:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= retry_count:
                break
            import asyncio
            import random

            await asyncio.sleep((2**attempt) + random.uniform(0, 0.5))
        finally:
            if page:
                await page.close()
            if context:
                await browser_manager.release_context(context)

    raise HTTPException(
        status_code=500,
        detail=f"Failed to fetch seller {user_id}: {last_error}",
    )
