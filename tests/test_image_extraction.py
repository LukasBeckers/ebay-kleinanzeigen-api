"""Regression tests for the gallery extractor.

Pre-fix the scraper used ``page.query_selector("#viewad-image")`` +
``.get_attribute("src")``, which only returned the cover thumbnail —
any listing with multiple photos came back as a list of length 1.
The fix moves to a pure-HTML helper that reads ``data-imgsrc`` from
every ``.galleryimage-element img`` under ``#viewad-image`` and
filters to the large-variant URL (``?rule=$_59.AUTO``) so the doubled
thumb URLs are deduped out.
"""
from pathlib import Path

import pytest

from libs.websites.kleinanzeigen import extract_gallery_image_urls

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def listing_detail_fixture_html() -> str:
    """Real Kleinanzeigen detail page for adid 2674165671 — a motorcycle
    listing with multiple gallery photos.  Captured live during the fix
    investigation; regenerate with:

        curl -sL -A 'Mozilla/5.0' \\
            'https://www.kleinanzeigen.de/s-anzeige/foo/2674165671' \\
            > tests/fixtures/listing_detail_2674165671.html
    """
    return (FIXTURES_DIR / "listing_detail_2674165671.html").read_text()


class TestExtractGalleryImageUrls:
    def test_returns_multiple_urls_from_real_listing(self, listing_detail_fixture_html):
        """The whole point of the fix: more than one image per listing."""
        urls = extract_gallery_image_urls(listing_detail_fixture_html)
        # The captured listing has 7 photos; assert ≥6 so the test
        # doesn't trip if the seller deletes one before the fixture is
        # regenerated.
        assert len(urls) >= 6, f"expected ≥6 gallery URLs, got {len(urls)}"

    def test_returns_only_large_variant_urls(self, listing_detail_fixture_html):
        """Every URL must be ``?rule=$_59.AUTO`` — the doubled ``$_57``
        thumb variant gets filtered out so each photo appears once."""
        urls = extract_gallery_image_urls(listing_detail_fixture_html)
        assert urls, "fixture should contain at least one URL"
        for url in urls:
            assert "?rule=$_59.AUTO" in url, f"non-large variant slipped through: {url}"
            assert "?rule=$_57.AUTO" not in url

    def test_returns_no_duplicates(self, listing_detail_fixture_html):
        urls = extract_gallery_image_urls(listing_detail_fixture_html)
        assert len(urls) == len(set(urls)), "duplicate URLs in output"

    def test_returns_kleinanzeigen_image_host(self, listing_detail_fixture_html):
        urls = extract_gallery_image_urls(listing_detail_fixture_html)
        for url in urls:
            assert url.startswith("https://img.kleinanzeigen.de/api/v1/prod-ads/images/"), (
                f"unexpected host in URL: {url}"
            )

    def test_returns_empty_for_page_without_gallery(self):
        """Deleted-listing / error pages have no ``#viewad-image``
        container — the helper should degrade gracefully rather than
        raising."""
        assert extract_gallery_image_urls("<html><body>nope</body></html>") == []
        assert extract_gallery_image_urls("") == []

    def test_returns_empty_when_container_has_no_gallery_elements(self):
        """Some sold-out listings ship the container but no children."""
        html = '<html><body><div class="vip-image-gallery"></div></body></html>'
        assert extract_gallery_image_urls(html) == []
