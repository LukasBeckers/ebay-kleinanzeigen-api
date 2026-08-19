"""Offline BeautifulSoup helpers mirroring live Playwright extraction."""

from __future__ import annotations

import json
import re

from bs4 import Tag

from scrapers.search_listings import SPONSORED_LI_CLASS_TOKENS


def is_sponsored_list_item(li: Tag | None) -> bool:
    if li is None:
        return False
    classes = set(li.get("class") or [])
    return any(token in classes for token in SPONSORED_LI_CLASS_TOKENS)


def _parse_json_ld(article: Tag) -> dict[str, str]:
    script = article.find("script", attrs={"type": "application/ld+json"})
    if not script or not script.string:
        return {}
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return {}
    return {
        "title": str(data.get("title") or ""),
        "description": str(data.get("description") or ""),
    }


def parse_legacy_article(article: Tag) -> dict[str, str] | None:
    adid = article.get("data-adid")
    href = article.get("data-href")
    if not adid or not href:
        return None
    if is_sponsored_list_item(article.find_parent("li")):
        return None

    title_el = article.select_one("h2.text-module-begin a.ellipsis")
    price_el = article.select_one("p.aditem-main--middle--price-shipping--price")
    desc_el = article.select_one("p.aditem-main--middle--description")
    date_el = article.select_one("div.aditem-main--top--right")
    loc_el = article.select_one("div.aditem-main--top--left")

    return {
        "adid": adid,
        "href": href,
        "title": title_el.get_text(strip=True) if title_el else "",
        "price": price_el.get_text(strip=True) if price_el else "",
        "description": desc_el.get_text(strip=True) if desc_el else "",
        "posted_at_raw": date_el.get_text(strip=True) if date_el else "",
        "location_raw": loc_el.get_text(strip=True) if loc_el else "",
    }


def parse_modern_article(article: Tag) -> dict[str, str] | None:
    adid = article.get("data-adid")
    href = article.get("data-href")
    if not adid or not href:
        return None
    if is_sponsored_list_item(article.find_parent("li")):
        return None

    ld = _parse_json_ld(article)
    desc_el = article.select_one("p.mb-xsmall.text-bodyRegular.text-onSurfaceSubdued")
    price_el = article.select_one("p.text-title3.font-strong.text-secondary")
    top_row = article.select_one("div.mb-xsmall.flex.items-start.justify-between")

    posted_at_raw = ""
    location_raw = ""
    if top_row:
        blocks = top_row.select(
            ":scope > div.flex.items-center.gap-xxsmall.text-onSurfaceNonessential"
        )
        if blocks:
            loc_spans = blocks[0].select("span")
            location_raw = " ".join(
                s.get_text(strip=True) for s in loc_spans if s.get_text(strip=True)
            )
        if len(blocks) >= 2:
            posted_at_raw = blocks[1].get_text(strip=True)

    title = ld.get("title", "")
    if not title:
        img = article.select_one('a[href*="/s-anzeige/"] img')
        if img and img.get("alt"):
            title = re.sub(r" Vorschau$", "", img["alt"]).strip()

    description = desc_el.get_text(strip=True) if desc_el else ld.get("description", "")

    return {
        "adid": adid,
        "href": href,
        "title": title,
        "price": price_el.get_text(strip=True) if price_el else "",
        "description": description,
        "posted_at_raw": posted_at_raw,
        "location_raw": location_raw,
    }


def parse_search_article(article: Tag) -> dict[str, str] | None:
    classes = set(article.get("class") or [])
    if "aditem" in classes:
        return parse_legacy_article(article)
    return parse_modern_article(article)


def article_is_modern_layout(article: Tag) -> bool:
    return "aditem" not in set(article.get("class") or [])