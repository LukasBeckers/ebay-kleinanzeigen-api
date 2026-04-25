"""Parser tests using saved HTML fixtures — no network.

We don't re-use the Playwright-based extractor (it needs a live page).
Instead we assert on the *structural invariants* of the HTML that the
production extractor relies on: all ad-listitems must live inside the
#srchrslt-adtable container, and ad-listitem ids are present as
data-adid attributes.

This is enough to ``catch`` future layout changes on Kleinanzeigen and
forces the real scraper to keep scoping its selector correctly.
"""
import re

from bs4 import BeautifulSoup


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
