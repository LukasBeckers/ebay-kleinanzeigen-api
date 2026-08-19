"""Search-results listing extraction for legacy and modern Kleinanzeigen card layouts."""

from __future__ import annotations

from typing import Any

SEARCH_ADTABLE_SELECTOR = "#srchrslt-adtable"
SEARCH_HYDRATION_SELECTOR = f"{SEARCH_ADTABLE_SELECTOR} article[data-adid]"
SEARCH_ARTICLE_SELECTOR = SEARCH_HYDRATION_SELECTOR

SPONSORED_LI_CLASS_TOKENS = (
    "is-topad",
    "badge-topad",
    "badge-hint-pro-small-srp",
)

EXTRACT_ARTICLE_JS = """
(article) => {
  const adid = article.getAttribute("data-adid");
  const href = article.getAttribute("data-href");
  if (!adid || !href) return null;

  const li = article.closest("li");
  if (li) {
    const liClass = li.className || "";
    for (const token of ["is-topad", "badge-topad", "badge-hint-pro-small-srp"]) {
      if (liClass.includes(token)) return null;
    }
  }

  const isLegacy = article.classList.contains("aditem");
  if (isLegacy) {
    const titleEl = article.querySelector("h2.text-module-begin a.ellipsis");
    const priceEl = article.querySelector("p.aditem-main--middle--price-shipping--price");
    const descEl = article.querySelector("p.aditem-main--middle--description");
    const dateEl = article.querySelector("div.aditem-main--top--right");
    const locEl = article.querySelector("div.aditem-main--top--left");
    return {
      adid,
      href,
      title: titleEl?.innerText?.trim() || "",
      price: priceEl?.innerText?.trim() || "",
      description: descEl?.innerText?.trim() || "",
      posted_at_raw: dateEl?.innerText?.trim() || "",
      location_raw: locEl?.innerText?.trim() || "",
    };
  }

  let title = "";
  let description = "";
  const ld = article.querySelector('script[type="application/ld+json"]');
  if (ld) {
    try {
      const data = JSON.parse(ld.textContent);
      title = data.title || "";
      description = data.description || "";
    } catch (e) {}
  }

  const descEl = article.querySelector("p.mb-xsmall.text-bodyRegular.text-onSurfaceSubdued");
  if (descEl) description = descEl.innerText.trim();

  const priceEl = article.querySelector("p.text-title3.font-strong.text-secondary");
  const price = priceEl?.innerText?.trim() || "";

  const topRow = article.querySelector("div.mb-xsmall.flex.items-start.justify-between");
  let posted_at_raw = "";
  let location_raw = "";
  if (topRow) {
    const blocks = topRow.querySelectorAll(
      ":scope > div.flex.items-center.gap-xxsmall.text-onSurfaceNonessential"
    );
    if (blocks.length >= 1) {
      const locSpans = blocks[0].querySelectorAll("span");
      const parts = [...locSpans].map((s) => s.innerText.trim()).filter(Boolean);
      location_raw = parts.join(" ");
    }
    if (blocks.length >= 2) {
      posted_at_raw = blocks[1].innerText.trim();
    }
  }

  if (!title) {
    const titleLink = article.querySelector('a[href*="/s-anzeige/"] img');
    const alt = titleLink?.getAttribute("alt") || "";
    title = alt.replace(/ Vorschau$/, "").trim();
  }

  return {
    adid,
    href,
    title,
    price,
    description,
    posted_at_raw,
    location_raw,
  };
}
"""


def normalize_price_text(price_text: str) -> str:
    return price_text.replace("€", "").replace("VB", "").replace(".", "").strip()


def raw_fields_to_listing(raw: dict[str, Any]) -> dict[str, Any]:
    from scrapers.dates import parse_listing_date
    from scrapers.locations import parse_location

    posted_at_raw = raw.get("posted_at_raw", "")
    location_raw = raw.get("location_raw", "")
    location_zip, location_city, distance_km = parse_location(location_raw)

    return {
        "adid": raw["adid"],
        "url": f"https://www.kleinanzeigen.de{raw['href']}",
        "title": raw.get("title", ""),
        "price": normalize_price_text(raw.get("price", "")),
        "description": raw.get("description", ""),
        "posted_at": parse_listing_date(posted_at_raw),
        "posted_at_raw": posted_at_raw,
        "location_zip": location_zip,
        "location_city": location_city,
        "distance_km": distance_km,
    }