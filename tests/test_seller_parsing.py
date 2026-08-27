"""Offline parser tests for listing-sidebar and seller-profile HTML."""

from pathlib import Path

import pytest

from libs.websites.seller import (
    extract_listing_seller,
    parse_seller_profile,
    parse_seller_shop,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestExtractListingSeller:
    def test_private_listing_has_userid_name_type_since(self):
        seller = extract_listing_seller(_read("listing_seller_sidebar.html"))
        assert seller["id"] == "15626332"
        assert seller["name"] == "Bernd"
        assert seller["type"] == "private"
        assert seller["since"] == "19.06.2013"
        assert seller["url"] == (
            "https://www.kleinanzeigen.de/s-bestandsliste.html?userId=15626332"
        )
        assert seller["shop_url"] is None

    def test_private_listing_has_no_profile_only_fields(self):
        seller = extract_listing_seller(_read("listing_seller_sidebar.html"))
        assert seller["followers"] is None
        assert seller["response_time"] is None
        assert seller["response_time_hours"] is None

    def test_empty_html_returns_empty_seller(self):
        seller = extract_listing_seller("<html></html>")
        assert seller["id"] is None
        assert seller["name"] is None


class TestParseSellerProfile:
    def test_andre_profile_core_fields(self):
        seller = parse_seller_profile(_read("seller_profile_private.html"))
        assert seller["id"] == "1"
        assert seller["name"] == "André"
        assert seller["type"] == "private"
        assert seller["since"] == "01.09.2009"
        assert seller["url"] == (
            "https://www.kleinanzeigen.de/s-bestandsliste.html?userId=1"
        )

    def test_andre_profile_badges(self):
        seller = parse_seller_profile(_read("seller_profile_private.html"))
        assert "TOP Zufriedenheit" in seller["badges"]
        assert "Besonders freundlich" in seller["badges"]
        assert "Besonders zuverlässig" in seller["badges"]

    def test_andre_profile_response_time_and_followers(self):
        seller = parse_seller_profile(_read("seller_profile_private.html"))
        assert seller["response_time"] == (
            "Antwortet in der Regel innerhalb von 3 Stunden"
        )
        assert seller["response_time_hours"] == 3
        assert seller["followers"] == 27

    def test_profile_without_response_time(self):
        seller = parse_seller_profile(_read("seller_profile_private_no_response.html"))
        assert seller["id"] == "15626332"
        assert seller["name"] == "Bernd"
        assert seller["response_time"] is None
        assert seller["response_time_hours"] is None
        assert seller["followers"] == 1


class TestParseSellerShop:
    def test_commercial_shop_identity_and_counts(self):
        seller = parse_seller_shop(_read("seller_shop_commercial.html"))
        assert seller["id"] == "66649529"
        assert seller["name"] == "4Traders GmbH"
        assert seller["type"] == "business"
        assert seller["since"] == "26.08.2019"
        assert seller["ads_online"] == 71
        assert seller["ads_total"] == 819
        assert seller["followers"] == 2073
        assert seller["shop_url"] == (
            "https://www.kleinanzeigen.de/pro/4-Traders-GmbH"
        )
        assert "TOP Zufriedenheit" in seller["badges"]
