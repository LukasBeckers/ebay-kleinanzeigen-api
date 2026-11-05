"""Listing detail fetches stay on one Kleinanzeigen path segment."""
import pytest
from fastapi import HTTPException

from scrapers.inserat import get_inserate_details_optimized


@pytest.mark.asyncio
async def test_detail_fetch_rejects_a_listing_id_before_navigation():
    with pytest.raises(HTTPException) as caught:
        await get_inserate_details_optimized(None, "..")
    assert caught.value.status_code == 400
