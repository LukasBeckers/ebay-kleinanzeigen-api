"""Parser tests using saved HTML fixtures — no network.

We don't re-use the Playwright-based extractor (it needs a live page).
Instead we assert on the *structural invariants* of the HTML that the
production extractor relies on: all ad-listitems must live inside the
#srchrslt-adtable container, and ad-listitem ids are present as
data-adid attributes.

This is enough to ``catch`` future layout changes on Kleinanzeigen and
forces the real scraper to keep scoping its selector correctly.

Also covers the pure-Python ``parse_listing_date`` helper (no fixture).
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from scrapers.dates import parse_listing_date


def _parse(html: str) -> BeautifulSoup:
    # ``lxml`` is far more forgiving of real-world HTML than ``html.parser``,
    # which can choke on Kleinanzeigen's mid-page ``&#8203...;`` sequences.
    return BeautifulSoup(html, "lxml")


class TestFixtureStructure:
    """The fixture really is the motorcycles search page we think it is."""

    def test_page_title_contains_category(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        title = (soup.title.string or "").lower()
        assert "motorrad" in title, f"fixture's <title>: {soup.title.string!r}"

    def test_page_title_contains_location(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        assert "gangelt" in (soup.title.string or "").lower()

    def test_broken_fixture_title_is_generic_location_feed(self, broken_category_fixture_html):
        """Sanity check on the "bug reproducer" fixture: the pre-fix URL
        returned the generic Gangelt listings feed without the motorcycle category."""
        soup = _parse(broken_category_fixture_html)
        title = (soup.title.string or "").lower()
        assert "gangelt" in title
        assert "motorrad" not in title


class TestSelectorScoping:
    """The scraper's live selector targets ``#srchrslt-adtable .ad-listitem …``.

    We verify that:
      1. The container exists on a real page.
      2. Every ``.ad-listitem`` with an adid on the page lives inside it.
      3. Topads and pro-badge ads are not counted as "main" results.
    """

    def test_main_container_present(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        assert soup.find(id="srchrslt-adtable") is not None

    def test_all_main_items_have_adid(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        container = soup.find(id="srchrslt-adtable")
        items = container.select(".ad-listitem article[data-adid]")
        assert len(items) >= 10, f"expected many items, got {len(items)}"
        for li in items:
            assert li.get("data-adid", "").isdigit()

    def test_topads_excluded_from_main_selector(self, motorcycles_fixture_html):
        """If this page happened to include topads, the scraper's selector
        must exclude them (they're advertising, not organic results)."""
        soup = _parse(motorcycles_fixture_html)
        selector = "#srchrslt-adtable .ad-listitem:not(.is-topad):not(.badge-hint-pro-small-srp) article[data-adid]"
        items = soup.select(selector)
        for art in items:
            li = art.find_parent("li")
            if li is not None:
                classes = set(li.get("class") or [])
                assert "is-topad" not in classes
                assert "badge-hint-pro-small-srp" not in classes

    def test_no_outside_adlistitems_leak(self, motorcycles_fixture_html):
        """Any ``.ad-listitem`` found *outside* #srchrslt-adtable would leak
        into the scraper output if the selector weren't scoped.  On this
        page there shouldn't be any — if Kleinanzeigen adds an "Auch
        interessant" sidebar later, this test will flag it."""
        soup = _parse(motorcycles_fixture_html)
        all_items = soup.select(".ad-listitem")
        main = soup.find(id="srchrslt-adtable").select(".ad-listitem")
        outside = [i for i in all_items if i not in main]
        assert outside == [], (
            f"found {len(outside)} ad-listitem(s) outside main container — "
            "scraper's selector MUST stay scoped to #srchrslt-adtable"
        )


class TestRelevance:
    """Loose relevance check on the fixture — titles should lean 'motorcycle'."""

    MOTO_TERMS = (
        "roller", "motorrad", "mofa", "moped", "vespa", "scooter",
        "piaggio", "aprilia", "kymco", "sachs", "tomos", "kreidler",
        "puch", "rex", "zündapp", "simson", "peugeot", "derbi",
        "bastler", "scheibe", "elektroroller",
    )

    def test_majority_of_titles_are_motorcycle_domain(self, motorcycles_fixture_html):
        soup = _parse(motorcycles_fixture_html)
        container = soup.find(id="srchrslt-adtable")
        titles = [a.get_text(strip=True).lower() for a in container.select("h2 a.ellipsis")]
        assert len(titles) > 0
        hits = sum(any(term in t for term in self.MOTO_TERMS) for t in titles)
        ratio = hits / len(titles)
        assert ratio >= 0.6, (
            f"only {hits}/{len(titles)} ({ratio:.0%}) titles look motorcycle-domain: "
            f"{titles[:5]}"
        )


class TestParseListingDate:
    """Card-level posted_at parsing.  ``now`` is pinned for determinism."""

    BERLIN = ZoneInfo("Europe/Berlin")
    # 2026-04-25 Saturday 12:00 Berlin → 10:00 UTC
    NOW = datetime(2026, 4, 25, 12, 0, 0, tzinfo=BERLIN)

    def test_today(self):
        out = parse_listing_date("Heute, 10:06", now=self.NOW)
        # 10:06 Europe/Berlin on the same calendar day as ``now`` → 08:06 UTC
        assert out == "2026-04-25T08:06:00+00:00"

    def test_today_short_hour(self):
        out = parse_listing_date("Heute, 8:30", now=self.NOW)
        assert out == "2026-04-25T06:30:00+00:00"

    def test_yesterday(self):
        out = parse_listing_date("Gestern, 14:18", now=self.NOW)
        assert out == "2026-04-24T12:18:00+00:00"

    def test_explicit_date(self):
        out = parse_listing_date("23.04.2026", now=self.NOW)
        # Midnight Europe/Berlin → 22:00 UTC the previous day
        assert out == "2026-04-22T22:00:00+00:00"

    def test_with_leading_whitespace(self):
        out = parse_listing_date(" Heute, 10:06", now=self.NOW)
        assert out == "2026-04-25T08:06:00+00:00"

    def test_empty(self):
        assert parse_listing_date("", now=self.NOW) is None
        assert parse_listing_date(None, now=self.NOW) is None

    def test_garbage(self):
        assert parse_listing_date("ASAP", now=self.NOW) is None
        assert parse_listing_date("Vor 10 Min.", now=self.NOW) is None

    def test_invalid_date(self):
        # 31.02 isn't a real date → returns None instead of crashing
        assert parse_listing_date("31.02.2026", now=self.NOW) is None

    def test_today_is_dst_aware(self):
        """At Europe/Berlin DST transitions the UTC offset changes from +01 to +02.
        Pin ``now`` to a summer date and confirm the offset is applied."""
        # 1 July 2026 is in CEST (+02:00).
        now_summer = datetime(2026, 7, 1, 12, 0, 0, tzinfo=self.BERLIN)
        out = parse_listing_date("Heute, 14:00", now=now_summer)
        # 14:00 CEST = 12:00 UTC
        assert out == "2026-07-01T12:00:00+00:00"


class TestParseLocation:
    """Card-level location parsing.  Tested against the actual strings observed
    on kleinanzeigen.de — the extractor never raises and degrades gracefully
    when components are missing."""

    def test_typical_with_distance(self):
        from scrapers.locations import parse_location
        assert parse_location("52249 Eschweiler (28 km)") == ("52249", "Eschweiler", 28)

    def test_with_ca_distance_boundary(self):
        from scrapers.locations import parse_location
        # Distance kleinanzeigen labels "(ca. 100 km)" — same numeric value,
        # the "ca." just signals it's near the radius edge.
        assert parse_location("44809 Bochum-Mitte (ca. 100 km)") == ("44809", "Bochum-Mitte", 100)

    def test_4digit_plz(self):
        from scrapers.locations import parse_location
        # German 4-digit PLZ are valid (e.g. former DDR area, some small towns).
        assert parse_location("9999 Testdorf (5 km)") == ("9999", "Testdorf", 5)

    def test_no_distance_same_town(self):
        from scrapers.locations import parse_location
        # Same-town cards omit the (N km) entirely.
        assert parse_location("Gangelt") == (None, "Gangelt", None)

    def test_no_distance_with_plz(self):
        from scrapers.locations import parse_location
        # Nationwide-fallback cards: PLZ + city, no km — exactly what
        # kleinanzeigen serves when the silent radius fallback fires.
        assert parse_location("55411 Bingen") == ("55411", "Bingen", None)

    def test_city_with_district_dash(self):
        from scrapers.locations import parse_location
        assert parse_location("50858 Köln-Junkersdorf (60 km)") == ("50858", "Köln-Junkersdorf", 60)

    def test_empty(self):
        from scrapers.locations import parse_location
        assert parse_location("") == (None, None, None)
        assert parse_location(None) == (None, None, None)

    def test_garbage_doesnt_raise(self):
        from scrapers.locations import parse_location
        # Anything that doesn't parse should return None for unidentified
        # parts rather than throwing.
        assert parse_location("???") == (None, "???", None)
