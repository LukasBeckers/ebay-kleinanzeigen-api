"""Pure URL-construction helpers for Kleinanzeigen search pages.

Kept free of Playwright / async / side effects so it's trivially unit-testable.
"""
from urllib.parse import urlencode

BASE_URL = "https://www.kleinanzeigen.de"

# Server-side sort options exposed by kleinanzeigen.de as query parameters.
# Confirmed by inspecting the live site's ``<ul id="sortingField-selector-list">``
# dropdown values.  ``None`` / ``"newest"`` is the site's default
# (``SORTING_DATE``) and emits no query parameter, so the URL stays
# byte-identical to what the builder produced before sort existed.
SORT_TOKENS: dict[str | None, str | None] = {
    None: None,
    "newest": None,
    "price_asc": "PRICE_AMOUNT",
    "price_desc": "PRICE_AMOUNT_DESC",
    "distance_asc": "DISTANCE",
}


def _price_path(min_price: int | None, max_price: int | None) -> str:
    if min_price is None and max_price is None:
        return ""
    lo = "" if min_price is None else str(min_price)
    hi = "" if max_price is None else str(max_price)
    return f"/preis:{lo}:{hi}"


def _sort_param(sort: str | None) -> str | None:
    if sort not in SORT_TOKENS:
        raise ValueError(
            f"unknown sort {sort!r}; allowed: {sorted(k for k in SORT_TOKENS if k)}"
        )
    return SORT_TOKENS[sort]


def build_search_url_template(
    *,
    query: str | None = None,
    location: str | None = None,
    radius: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    category: str | None = None,
    sort: str | None = None,
) -> str:
    """Return a URL with a literal ``{page}`` placeholder for the page number.

    Two URL shapes, matching what kleinanzeigen.de actually serves today:

    * **No category** — the category-free "search" path:
      ``/preis:MIN:MAX/s-seite:{page}?keywords=&locationStr=&radius=&sortingField=...``
    * **With category** — slug + price + seite + ``cNNN`` suffix.
      Kleinanzeigen requires a slug segment before ``/c<id>``; any non-empty
      slug resolves via the ``cNNN`` id, so we use ``/s-`` as a placeholder.
      Putting ``/c<id>`` at the end (not in the middle) is what makes the
      category actually apply:
      ``/s-/preis:MIN:MAX/seite:{page}/c<id>?locationStr=&radius=&keywords=&sortingField=...``

    The previous format ``/cNNN/s-seite:{page}?…`` silently dropped the category
    (returned a generic location feed). That's the bug this function fixes.

    Sort is applied via the ``sortingField`` **query parameter** (verified by
    inspecting the site's own dropdown markup; the path-slug ``/sortierung:``
    form looks valid but kleinanzeigen ignores it server-side and falls back
    to default newest-first).  ``sort=None`` (or ``"newest"``) emits no
    ``sortingField`` parameter at all so the URL stays byte-identical to what
    the builder produced before sort existed.
    """
    price = _price_path(min_price, max_price)

    cat = category.lstrip("c") if category else ""
    if cat:
        path = f"/s-{price}/seite:{{page}}/c{cat}"
    else:
        path = f"{price}/s-seite:{{page}}"

    params: dict[str, str] = {}
    if query:
        params["keywords"] = query
    if location:
        params["locationStr"] = location
    if radius:
        params["radius"] = str(radius)
    sort_value = _sort_param(sort)
    if sort_value:
        params["sortingField"] = sort_value

    qs = f"?{urlencode(params)}" if params else ""
    return f"{BASE_URL}{path}{qs}"


def build_search_url(page: int, **kwargs) -> str:
    """Convenience: build a concrete URL for a specific page number."""
    return build_search_url_template(**kwargs).format(page=page)
