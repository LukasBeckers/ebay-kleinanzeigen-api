"""Unit tests for ``scrapers.url_builder``.

Written from the *contract* side — we assert URLs that kleinanzeigen.de
actually serves correctly for each combination.  Verified by live fetching
during the bug-hunt session; see tests/fixtures/ for snapshots.
"""
from scrapers.url_builder import build_search_url, build_search_url_template


class TestNoCategory:
    """When no category is given, fall back to Kleinanzeigen's keyword-search format."""

    def test_keyword_only(self):
        url = build_search_url(page=1, query="mofa")
        assert url == "https://www.kleinanzeigen.de/s-seite:1?keywords=mofa"

    def test_keyword_with_location(self):
        url = build_search_url(page=1, query="mofa", location="52538", radius=100)
        assert url == (
            "https://www.kleinanzeigen.de/s-seite:1"
            "?keywords=mofa&locationStr=52538&radius=100"
        )

    def test_price_range(self):
        url = build_search_url(page=2, query="mofa", min_price=0, max_price=300)
        assert url == (
            "https://www.kleinanzeigen.de/preis:0:300/s-seite:2?keywords=mofa"
        )

    def test_open_ended_min(self):
        url = build_search_url(page=1, query="x", max_price=100)
        # Kleinanzeigen accepts an empty segment before ``:``
        assert "/preis::100/" in url

    def test_open_ended_max(self):
        url = build_search_url(page=1, query="x", min_price=50)
        assert "/preis:50:/" in url


class TestWithCategory:
    """Category *must* be placed at path end as ``/c<id>`` AND requires a slug segment.

    Regression: the previous builder produced ``/cNNN/s-seite:N?…`` which
    kleinanzeigen.de silently turned into a generic location feed (the TV-
    results bug).
    """

    def test_category_only(self):
        url = build_search_url(page=1, category="305")
        # Any non-empty slug works; we use ``/s-`` as a minimal placeholder.
        assert url == "https://www.kleinanzeigen.de/s-/seite:1/c305"

    def test_category_prefix_c_tolerated(self):
        # Users may pass "c305" or "305" — both should produce the same URL.
        assert build_search_url(page=1, category="c305") == build_search_url(page=1, category="305")

    def test_category_with_location(self):
        url = build_search_url(page=1, category="305", location="52538", radius=100)
        assert url == (
            "https://www.kleinanzeigen.de/s-/seite:1/c305"
            "?locationStr=52538&radius=100"
        )

    def test_category_with_price_and_location(self):
        url = build_search_url(
            page=1,
            category="305",
            location="52538",
            radius=100,
            min_price=0,
            max_price=300,
        )
        assert url == (
            "https://www.kleinanzeigen.de/s-/preis:0:300/seite:1/c305"
            "?locationStr=52538&radius=100"
        )

    def test_category_with_keyword(self):
        url = build_search_url(page=1, query="mofa", category="305")
        assert url == (
            "https://www.kleinanzeigen.de/s-/seite:1/c305?keywords=mofa"
        )

    def test_category_bug_regression_no_bare_category_path(self):
        """Regression guard: the old buggy format ``/cNNN/s-seite:N`` should never
        appear again; Kleinanzeigen returns a generic location feed for it."""
        for url in [
            build_search_url(page=1, category="305", location="52538", radius=100),
            build_search_url(page=1, category="305"),
            build_search_url(page=3, category="305", max_price=300),
        ]:
            assert "/c305/s-seite" not in url, f"reverted to broken format: {url}"
            assert "/seite:" in url
            assert url.endswith("/c305") or "/c305?" in url


class TestPagination:
    def test_template_has_literal_placeholder(self):
        tpl = build_search_url_template(query="mofa")
        assert "{page}" in tpl

    def test_page_substitution(self):
        tpl = build_search_url_template(query="mofa")
        assert tpl.format(page=5) == "https://www.kleinanzeigen.de/s-seite:5?keywords=mofa"

    def test_page_substitution_with_category(self):
        tpl = build_search_url_template(category="305", location="52538", radius=100)
        assert tpl.format(page=7) == (
            "https://www.kleinanzeigen.de/s-/seite:7/c305?locationStr=52538&radius=100"
        )
