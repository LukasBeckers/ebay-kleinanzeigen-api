"""Pure-HTML seller extractors (listing sidebar, private profile, /pro/ shop)."""

from __future__ import annotations

import html as htmlmod
import re
from typing import Any

from bs4 import BeautifulSoup

PROFILE_URL = "https://www.kleinanzeigen.de/s-bestandsliste.html?userId={user_id}"
SHOP_URL_PREFIX = "https://www.kleinanzeigen.de"


def empty_seller() -> dict[str, Any]:
    return {
        "id": None,
        "name": None,
        "type": "private",
        "since": None,
        "badges": [],
        "url": None,
        "shop_url": None,
        "response_time": None,
        "response_time_hours": None,
        "followers": None,
        "ads_online": None,
        "ads_total": None,
    }


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = htmlmod.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_user_id(text: str) -> str | None:
    for pat in (
        r"[?&]userId=(\d+)",
        r's-anzeigen-des-nutzers/(\d+)',
        r'profileUserId\s*=\s*"(\d+)"',
        r'data-followed-user="(\d+)"',
        r'const userId = "(\d+)"',
        r'&quot;userId&quot;:\[0,&quot;(\d+)&quot;\]',
        r'"userId"\s*:\s*"(\d+)"',
    ):
        m = re.search(pat, text)
        if m and m.group(1) != "0":
            return m.group(1)
    return None


def _parse_since(text: str) -> str | None:
    m = re.search(r"Aktiv\s+seit\s+(\d{1,2}\.\d{1,2}\.\d{4})", text, re.I)
    return m.group(1) if m else None


def _parse_type(text: str) -> str:
    if re.search(r"Gewerblich(?:er)?\s+(?:Nutzer|Anbieter)", text, re.I):
        return "business"
    return "private"


def _parse_followers(text: str) -> int | None:
    m = re.search(r"([\d.]+)\s+Follower", text, re.I)
    if not m:
        return None
    return int(m.group(1).replace(".", ""))


def _parse_response_time(text: str) -> tuple[str | None, int | None]:
    m = re.search(
        r"(Antwortet in der Regel innerhalb von\s+(\d+)\s+Stunden)",
        text,
        re.I,
    )
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def _parse_ads_counts(text: str) -> tuple[int | None, int | None]:
    online = None
    total = None
    m = re.search(r"([\d.]+)\s+Anzeigen\s+online", text, re.I)
    if m:
        online = int(m.group(1).replace(".", ""))
    m = re.search(r"([\d.]+)\s+Anzeigen\s+gesamt", text, re.I)
    if m:
        total = int(m.group(1).replace(".", ""))
    return online, total


def _parse_shop_url(text: str) -> str | None:
    m = re.search(r'(/pro/[A-Za-z0-9][A-Za-z0-9._-]*)', text)
    if not m:
        return None
    slug = m.group(1).rstrip(".,;\"'")
    return f"{SHOP_URL_PREFIX}{slug}"


def _badge_texts(soup: BeautifulSoup) -> list[str]:
    badges: list[str] = []
    seen: set[str] = set()
    for el in soup.select(".userbadge-tag, [data-testid^='user-badge-']"):
        label = _clean(el.get_text(" ", strip=True))
        if not label or label in seen:
            continue
        seen.add(label)
        badges.append(label)
    return badges


def _profile_url(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return PROFILE_URL.format(user_id=user_id)


def extract_listing_seller(html: str) -> dict[str, Any]:
    """Seller fields available on a listing detail (VIP) page."""
    seller = empty_seller()
    soup = BeautifulSoup(html, "html.parser")
    seller["id"] = _parse_user_id(html)

    name_el = soup.select_one(".userprofile-vip")
    if name_el:
        seller["name"] = _clean(name_el.get_text(" ", strip=True)) or None

    box = soup.select_one("#viewad-profile-box") or soup
    box_text = box.get_text(" ", strip=True)
    seller["type"] = _parse_type(box_text)
    seller["since"] = _parse_since(box_text)
    seller["badges"] = _badge_texts(box)
    seller["url"] = _profile_url(seller["id"])
    seller["shop_url"] = _parse_shop_url(html)
    return seller


def parse_seller_profile(html: str, user_id: str | None = None) -> dict[str, Any]:
    """Private (and some commercial) profile page: /s-bestandsliste.html?userId=."""
    seller = empty_seller()
    soup = BeautifulSoup(html, "html.parser")
    seller["id"] = user_id or _parse_user_id(html)

    name_el = soup.select_one("h2.userprofile--name")
    if name_el:
        # Drop the sr-only "Profil von" prefix.
        for hidden in name_el.select(".sr-only"):
            hidden.decompose()
        seller["name"] = _clean(name_el.get_text(" ", strip=True)) or None
    if not seller["name"]:
        title = soup.title.string if soup.title else ""
        m = re.search(r"Alle Anzeigen von\s+(.+?)\s+\|", title or "")
        if m:
            seller["name"] = _clean(m.group(1))

    info = soup.select_one(".userprofile-info") or soup
    info_text = info.get_text(" ", strip=True)
    seller["type"] = _parse_type(info_text)
    seller["since"] = _parse_since(info_text)
    seller["followers"] = _parse_followers(info_text)
    raw_rt, hours = _parse_response_time(info_text)
    seller["response_time"] = raw_rt
    seller["response_time_hours"] = hours
    seller["ads_online"], seller["ads_total"] = _parse_ads_counts(info_text)
    seller["badges"] = _badge_texts(soup)
    seller["url"] = _profile_url(seller["id"])
    seller["shop_url"] = _parse_shop_url(html)
    return seller


def parse_seller_shop(html: str, user_id: str | None = None) -> dict[str, Any]:
    """Commercial /pro/{slug} shop page."""
    seller = empty_seller()
    soup = BeautifulSoup(html, "html.parser")
    seller["id"] = user_id or _parse_user_id(html)

    ld = soup.find("script", type="application/ld+json")
    if ld and ld.string:
        import json

        try:
            data = json.loads(ld.string)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            seller["name"] = data.get("name") or seller["name"]
            url = data.get("url") or ""
            if "/pro/" in str(url):
                # Canonicalize to public host.
                m = re.search(r"/pro/[A-Za-z0-9._-]+", str(url))
                if m:
                    seller["shop_url"] = f"{SHOP_URL_PREFIX}{m.group(0)}"

    if not seller["name"]:
        h1 = soup.find("h1")
        if h1:
            seller["name"] = _clean(h1.get_text(" ", strip=True)) or None
    if not seller["name"] and soup.title:
        seller["name"] = _clean((soup.title.string or "").split("|")[0]) or None

    text = soup.get_text(" ", strip=True)
    seller["type"] = "business"
    seller["since"] = _parse_since(text)
    seller["followers"] = _parse_followers(text)
    seller["ads_online"], seller["ads_total"] = _parse_ads_counts(text)
    seller["badges"] = _badge_texts(soup)
    if not seller["shop_url"]:
        seller["shop_url"] = _parse_shop_url(html)
    seller["url"] = _profile_url(seller["id"])
    return seller
