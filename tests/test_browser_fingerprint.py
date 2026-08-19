"""Unit tests for the coherent Chromium / de-DE Playwright fingerprint."""

from utils.browser import build_fingerprint
from utils.user_agent import _CHROME_BUILD, _USER_AGENTS, get_random_ua


def test_user_agent_matches_playwright_chromium_build():
    ua = get_random_ua()
    assert f"Chrome/{_CHROME_BUILD}" in ua
    assert "Firefox" not in ua
    assert "Version/" not in ua  # Safari UA token


def test_build_fingerprint_is_coherent_de_de_chromium():
    fp = build_fingerprint()
    assert fp["locale"] == "de-DE"
    assert fp["timezone_id"] == "Europe/Berlin"
    assert fp["viewport"] == {"width": 1440, "height": 900}
    assert fp["extra_http_headers"]["Accept-Language"] == "de-DE,de;q=0.9"
    assert f"Chrome/{_CHROME_BUILD}" in fp["user_agent"]
    assert fp["user_agent"] in _USER_AGENTS
