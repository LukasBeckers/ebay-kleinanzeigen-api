"""
Ultra-optimized router for maximum performance scraping.
"""

import json

from fastapi import APIRouter, Query, Request, HTTPException
from scrapers.inserate_ultra_optimized import ultra_optimized_scrape_inserate

router = APIRouter()


@router.get("/inserate")
async def get_inserate_ultra_optimized(
    request: Request,
    query: str = Query(None, description="Search query string"),
    location: str = Query(None, description="Location filter"),
    radius: int = Query(None, description="Search radius in kilometers"),
    min_price: int = Query(None, description="Minimum price filter"),
    max_price: int = Query(None, description="Maximum price filter"),
    page_count: int = Query(1, ge=1, le=20, description="Number of pages to fetch"),
    category: str = Query(None, description="Kleinanzeigen category id (e.g. '305' for motorcycles)"),
    sort: str = Query(
        None,
        description="Server-side sort: newest | price_asc | price_desc | distance_asc",
        pattern="^(newest|price_asc|price_desc|distance_asc)$",
    ),
    attribute_filters: str = Query(
        None,
        description=(
            "JSON-encoded dict of category-specific filters appended to /c<id> as "
            "+key:value segments. Range values use comma: '<min>,<max>'. Example: "
            '{"motorraeder_roller.km_i": ",50000"}'
        ),
    ),
):
    """
    Fetch listings based on search criteria.

    Retrieves listings from Kleinanzeigen with support for various filters
    including location, price range, and search terms. Results are returned
    with performance metrics and success indicators.
    """
    browser_manager = request.app.state.browser_manager
    if not browser_manager:
        raise HTTPException(status_code=503, detail="Service unavailable")

    parsed_attribute_filters: dict[str, str] | None = None
    if attribute_filters:
        try:
            parsed_attribute_filters = json.loads(attribute_filters)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"attribute_filters not JSON: {e}")
        if not isinstance(parsed_attribute_filters, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in parsed_attribute_filters.items()
        ):
            raise HTTPException(
                status_code=400,
                detail="attribute_filters must be a JSON object of string→string",
            )

    try:
        # Execute ultra-optimized scraping
        result = await ultra_optimized_scrape_inserate(
            browser_manager=browser_manager,
            query=query,
            location=location,
            radius=radius,
            min_price=min_price,
            max_price=max_price,
            page_count=page_count,
            category=category,
            sort=sort,
            attribute_filters=parsed_attribute_filters,
        )

        # Clean up response - remove excessive metrics for production
        if "task_metrics" in result:
            del result["task_metrics"]
        if "optimization_features" in result:
            del result["optimization_features"]

        # Simplify performance metrics
        if "performance_metrics" in result:
            metrics = result["performance_metrics"]
            # Keep only essential metrics
            essential_metrics = {
                "pages_requested": metrics.get("pages_requested", 0),
                "pages_successful": metrics.get("pages_successful", 0),
                "success_rate": metrics.get("success_rate", 0),
                "average_page_time": metrics.get("average_page_time", 0),
            }
            result["performance_metrics"] = essential_metrics

        return result

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
