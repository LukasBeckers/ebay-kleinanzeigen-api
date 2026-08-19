"""Offline tests for dual-layout search listing extraction."""

from bs4 import BeautifulSoup

from scrapers.search_listings import (
    SEARCH_ARTICLE_SELECTOR,
    SEARCH_HYDRATION_SELECTOR,
    raw_fields_to_listing,
)
from tests.search_listings_parsing import (
    article_is_modern_layout,
    parse_search_article,
)


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class TestLegacyLayoutParsing:
    def test_legacy_fixture_matches_hydration_selector(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        articles = soup.select(SEARCH_HYDRATION_SELECTOR)
        assert len(articles) >= 10

    def test_legacy_article_fields(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        article = soup.select_one(
            "#srchrslt-adtable .ad-listitem:not(.is-topad) article[data-adid]"
        )
        raw = parse_search_article(article)
        listing = raw_fields_to_listing(raw)

        assert raw["adid"].isdigit()
        assert raw["href"].startswith("/s-anzeige/")
        assert listing["title"]
        assert listing["url"].startswith("https://www.kleinanzeigen.de")
        assert not article_is_modern_layout(article)


class TestModernLayoutParsing:
    def test_modern_fixture_has_no_ad_listitem(self, modern_layout_fixture_html):
        soup = _parse(modern_layout_fixture_html)
        container = soup.find(id="srchrslt-adtable")
        assert container.select(".ad-listitem") == []
        assert len(container.select('li[data-clickable="card"]')) >= 1

    def test_modern_fixture_matches_layout_agnostic_selector(
        self, modern_layout_fixture_html
    ):
        soup = _parse(modern_layout_fixture_html)
        articles = soup.select(SEARCH_ARTICLE_SELECTOR)
        assert len(articles) == 2

    def test_modern_article_fields(self, modern_layout_fixture_html):
        soup = _parse(modern_layout_fixture_html)
        article = soup.select_one(
            '#srchrslt-adtable article[data-adid="3451936094"]'
        )
        raw = parse_search_article(article)
        listing = raw_fields_to_listing(raw)

        assert raw["title"] == "E Scooter/Roller/ Elektro"
        assert raw["price"] == "200 € VB"
        assert raw["posted_at_raw"] == "Heute, 22:12"
        assert "Erkrath" in raw["location_raw"]
        assert listing["location_city"] == "Erkrath"
        assert listing["location_zip"] == "40699"
        assert listing["distance_km"] == 70
        assert article_is_modern_layout(article)

    def test_modern_topad_excluded(self, modern_layout_fixture_html):
        soup = _parse(modern_layout_fixture_html)
        article = soup.select_one(
            '#srchrslt-adtable article[data-adid="9999999999"]'
        )
        assert parse_search_article(article) is None