from typing import Dict, List, Optional, Union, Any
from bs4 import BeautifulSoup
from playwright.async_api import Page, ElementHandle


async def get_element_content(
    page: Page, selector: str, default: Any = None
) -> Optional[str]:
    element: Optional[ElementHandle] = await page.query_selector(selector)
    if element:
        return await element.inner_text()
    return default


async def get_elements_content(page: Page, selector: str) -> List[str]:
    elements: List[ElementHandle] = await page.query_selector_all(selector)
    return [await element.text_content() for element in elements]


# Kleinanzeigen lazy-loads gallery images via the ``data-imgsrc`` attribute,
# not ``src``.  Each picture appears twice on a detail page: once with
# ``?rule=$_57.AUTO`` (small thumb in the carousel bar) and once with
# ``?rule=$_59.AUTO`` (large viewport-sized image).  We keep only the large
# variant so the returned list is one URL per actual photo.
_LARGE_IMAGE_RULE = "?rule=$_59.AUTO"


def extract_gallery_image_urls(html: str) -> List[str]:
    """Pure-HTML gallery extractor.  Returns one URL per actual photo on
    the listing's detail page, large-variant only, in DOM order.

    Splitting the extraction out of the Playwright call lets us
    regression-test against a saved HTML fixture without spinning up a
    full browser context.  Returns ``[]`` for pages with no gallery
    (deleted listings, error pages, etc.).

    Gallery DOM (Kleinanzeigen, 2026):

      <div class="vip-image-gallery galleryimage-large ...">      ← container
        <div class="galleryimage-element ...">                    ← one per photo
          <img src="..." data-imgsrc="...?rule=$_57.AUTO" ...>    ← thumb variant
          <img src="..." data-imgsrc="...?rule=$_59.AUTO" ...>    ← large variant
        </div>
        ...
      </div>

    Note: ``id="viewad-image"`` is on each ``<img>``, not on the wrapper
    (multiple-ID HTML; surprising, but that's how Kleinanzeigen ships
    it) — so we anchor on the wrapper's class, not the id.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one(".vip-image-gallery")
    if not container:
        return []
    urls: List[str] = []
    seen = set()
    for img in container.select(".galleryimage-element img[data-imgsrc]"):
        url = img.get("data-imgsrc") or ""
        if _LARGE_IMAGE_RULE not in url:
            continue  # drop the doubled-up thumb-rule variants
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


async def get_image_sources(page: Page, selector: str = "#viewad-image") -> List[str]:
    """Playwright wrapper around :func:`extract_gallery_image_urls`.

    Pre-fix this used ``query_selector`` (singular) + the plain ``src``
    attribute, which only captured the cover thumbnail — a listing with
    17 photos came back as a list of length 1.  The fix delegates to a
    pure-HTML helper that reads ``data-imgsrc`` from every gallery
    element under ``#viewad-image``.  The ``selector`` arg is kept for
    backward compatibility with existing callers; it's ignored when it
    equals the default ``"#viewad-image"``.
    """
    html = await page.content()
    return extract_gallery_image_urls(html)


def parse_price(price_text: Optional[str]) -> Dict[str, Union[str, bool]]:
    if not price_text:
        return {"amount": "0", "currency": "€", "negotiable": False}

    price_text = price_text.strip()
    negotiable: bool = "VB" in price_text

    price_text = price_text.replace("VB", "").strip()

    amount: str = price_text.replace("€", "").replace(".", "").replace(",", ".").strip()

    return {"amount": amount, "currency": "€", "negotiable": negotiable}


async def get_seller_details(page: Page) -> Dict[str, Optional[str]]:
    """Listing-sidebar seller. Profile-only fields (followers, Antwortzeit)
    stay None here — use ``GET /seller/{user_id}`` for those."""
    from libs.websites.seller import extract_listing_seller

    try:
        html = await page.content()
        parsed = extract_listing_seller(html)
        parsed["user_id"] = parsed.get("id")
        return parsed
    except Exception as e:
        print(f"Error getting seller details: {str(e)}")
        return {
            "name": None,
            "user_id": None,
            "id": None,
            "since": None,
            "type": "private",
            "badges": [],
            "url": None,
            "shop_url": None,
            "response_time": None,
            "response_time_hours": None,
            "followers": None,
            "ads_online": None,
            "ads_total": None,
        }


async def get_details(page: Page) -> Dict[str, str]:
    details: Dict[str, str] = {}
    try:
        # Get all detail items
        detail_items: List[ElementHandle] = await page.query_selector_all(
            "#viewad-details .addetailslist--detail"
        )

        for item in detail_items:
            # Extract label (everything before the span)
            content: str = await item.text_content()
            # Find the span element inside
            value_span: Optional[ElementHandle] = await item.query_selector(
                ".addetailslist--detail--value"
            )

            if value_span:
                value: str = await value_span.text_content()
                # The label is the content without the value
                label: str = content.replace(value, "").strip()
                details[label] = value.strip()
    except Exception as e:
        print(f"Error getting details: {str(e)}")

    return details


async def get_features(page: Page) -> List[str]:
    features: List[str] = []
    try:
        feature_elements: List[ElementHandle] = await page.query_selector_all(
            "#viewad-configuration .checktaglist .checktag"
        )
        for feature in feature_elements:
            feature_text: str = await feature.text_content()
            if feature_text and feature_text.strip():
                features.append(feature_text.strip())
    except Exception as e:
        print(f"Error getting features: {str(e)}")

    return features


async def get_location(page: Page) -> Dict[str, str]:
    location: Optional[str] = await get_element_content(page, "#viewad-locality")
    if not location:
        return {"zip": "", "city": "", "state": ""}

    location_parts: List[str] = (
        location.split(" - ") if " - " in location else [location]
    )

    first_part: str = location_parts[0].strip()
    zip_state_parts: List[str] = first_part.split(" ", 1)
    zip_code: str = zip_state_parts[0].strip()
    state: str = zip_state_parts[1].strip() if len(zip_state_parts) > 1 else ""

    city: str = location_parts[1].strip() if len(location_parts) > 1 else ""

    return {"zip": zip_code, "city": city, "state": state}


async def get_extra_info(page: Page) -> Dict[str, Optional[str]]:
    result: Dict[str, Optional[str]] = {"created_at": None, "views": "0"}

    try:
        date_element: Optional[ElementHandle] = await page.query_selector(
            "#viewad-extra-info > div:nth-child(1) > span"
        )
        if date_element:
            result["created_at"] = await date_element.inner_text()

        views_element: Optional[ElementHandle] = await page.query_selector(
            "#viewad-cntr-num"
        )
        if views_element:
            result["views"] = await views_element.inner_text()
    except Exception as e:
        print(f"Error getting extra info: {str(e)}")

    return result
