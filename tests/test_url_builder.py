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


class TestSort:
    """Server-side sort options exposed as ``/sortierung:<token>`` path slug."""

    def test_default_emits_no_segment(self):
        url = build_search_url(page=1, query="mofa")
        assert "/sortierung:" not in url

    def test_explicit_newest_emits_no_segment(self):
        # ``newest`` is the kleinanzeigen default, so it omits the slug
        # — explicit "newest" must produce a URL byte-identical to the
        # no-sort URL (otherwise we'd be surfacing a redirect-prone form).
        no_sort = build_search_url(page=1, query="mofa")
        explicit = build_search_url(page=1, query="mofa", sort="newest")
        assert no_sort == explicit

    def test_price_asc_appends_sortingField_param(self):
        url = build_search_url(page=1, query="mofa", min_price=0, max_price=300, sort="price_asc")
        # Sort travels as a query parameter (path-slug form is silently ignored).
        assert "sortingField=PRICE_AMOUNT" in url
        # And the path itself remains the standard newest-first shape.
        assert "/preis:0:300/s-seite:1" in url

    def test_price_desc_with_category(self):
        url = build_search_url(page=2, category="305", location="52538", radius=100, sort="price_desc")
        assert url == (
            "https://www.kleinanzeigen.de/s-/seite:2/c305"
            "?locationStr=52538&radius=100&sortingField=PRICE_AMOUNT_DESC"
        )

    def test_distance_asc(self):
        url = build_search_url(page=1, location="52538", radius=100, sort="distance_asc")
        assert "sortingField=DISTANCE" in url

    def test_unknown_value_raises(self):
        import pytest as _pt
        with _pt.raises(ValueError):
            build_search_url(page=1, query="x", sort="random")


class TestAttributeFilters:
    """Category-specific filters travel as ``+key:value`` segments appended
    to the ``/c<id>`` slug. Verified live against c305 (motorcycles):

    * enum:  ``+motorraeder_roller.type_s:motorrad``
    * range: ``+motorraeder_roller.km_i:,50000`` (open lower bound)
    """

    def test_enum_filter_appends_to_category(self):
        url = build_search_url(
            page=1,
            category="305",
            attribute_filters={"motorraeder_roller.type_s": "motorrad"},
        )
        assert url == (
            "https://www.kleinanzeigen.de/s-/seite:1/c305+motorraeder_roller.type_s:motorrad"
        )

    def test_range_filter_uses_comma_separator(self):
        url = build_search_url(
            page=1,
            category="305",
            attribute_filters={"motorraeder_roller.km_i": "10000,50000"},
        )
        assert "/c305+motorraeder_roller.km_i:10000,50000" in url

    def test_range_filter_open_lower_bound(self):
        # max-only is encoded with leading comma — verified live; min=0 is dropped by the site's JS.
        url = build_search_url(
            page=1,
            category="305",
            attribute_filters={"motorraeder_roller.km_i": ",50000"},
        )
        assert "/c305+motorraeder_roller.km_i:,50000" in url

    def test_multiple_filters_chain(self):
        url = build_search_url(
            page=1,
            category="305",
            attribute_filters={
                "motorraeder_roller.type_s": "motorrad",
                "motorraeder_roller.km_i": ",50000",
            },
        )
        # Order follows dict-insertion order (Python 3.7+).
        assert url.endswith(
            "/c305+motorraeder_roller.type_s:motorrad+motorraeder_roller.km_i:,50000"
        )

    def test_filter_with_location_and_price(self):
        url = build_search_url(
            page=2,
            category="305",
            location="52538",
            radius=100,
            min_price=0,
            max_price=300,
            attribute_filters={"motorraeder_roller.type_s": "mofa"},
        )
        assert url == (
            "https://www.kleinanzeigen.de/s-/preis:0:300/seite:2"
            "/c305+motorraeder_roller.type_s:mofa"
            "?locationStr=52538&radius=100"
        )

    def test_empty_dict_is_no_op(self):
        no_attrs = build_search_url(page=1, category="305")
        with_empty = build_search_url(page=1, category="305", attribute_filters={})
        assert no_attrs == with_empty

    def test_attribute_filters_require_category(self):
        import pytest as _pt
        with _pt.raises(ValueError, match="category"):
            build_search_url(page=1, attribute_filters={"foo.bar": "baz"})


class TestDefaultSnapshot:
    """Backwards-compat: existing callers (proxy, hunter) pass no ``sort`` arg.

    Their URLs MUST stay byte-identical to before this parameter existed.
    """

    SNAPSHOTS = [
        # (kwargs, expected URL for page 1)
        (dict(query="mofa"), "https://www.kleinanzeigen.de/s-seite:1?keywords=mofa"),
        (
            dict(query="mofa", location="52538", radius=100),
            "https://www.kleinanzeigen.de/s-seite:1?keywords=mofa&locationStr=52538&radius=100",
        ),
        (
            dict(category="305", location="52538", radius=75, min_price=30, max_price=200),
            "https://www.kleinanzeigen.de/s-/preis:30:200/seite:1/c305?locationStr=52538&radius=75",
        ),
    ]

    def test_no_sort_kwarg_byte_identical(self):
        for kwargs, expected in self.SNAPSHOTS:
            assert build_search_url(page=1, **kwargs) == expected

    def test_sort_none_byte_identical(self):
        for kwargs, expected in self.SNAPSHOTS:
            assert build_search_url(page=1, sort=None, **kwargs) == expected
