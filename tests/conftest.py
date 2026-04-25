"""Shared test fixtures.

All unit tests must stay offline — live tests live behind the ``live`` marker.
"""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def motorcycles_fixture_html() -> str:
    """A real Kleinanzeigen search result page for:
    category=305 (Motorcycles), location=52538 (Gangelt), radius=100, max_price=300.
    """
    return (FIXTURES_DIR / "motorcycles_gangelt_52538_under300.html").read_text()


@pytest.fixture(scope="session")
def broken_category_fixture_html() -> str:
    """The page returned by the PRE-fix URL ``/c305/s-seite:1?locationStr=...``.

    Category was silently ignored → Kleinanzeigen served a generic location
    feed.  Useful for asserting that after the fix we do NOT get this page.
    """
    return (FIXTURES_DIR / "broken_category_ignored.html").read_text()
