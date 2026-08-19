from fastapi import APIRouter, HTTPException, Request

from scrapers.seller import get_seller_profile

router = APIRouter()


@router.get("/seller/{user_id}")
async def get_seller(request: Request, user_id: str):
    """Scrape a Kleinanzeigen seller profile (bestandsliste + /pro/ shop)."""
    if not user_id or not user_id.strip() or not user_id.strip().isdigit():
        raise HTTPException(status_code=400, detail="Invalid seller user_id")

    browser_manager = request.app.state.browser_manager
    if not browser_manager:
        raise HTTPException(status_code=503, detail="Service unavailable")

    return await get_seller_profile(browser_manager, user_id.strip())
