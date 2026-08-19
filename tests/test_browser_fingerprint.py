"""Unit tests for the coherent Chromium / de-DE Playwright fingerprint."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from utils.browser import OptimizedPlaywrightManager, build_fingerprint
from utils.user_agent import get_random_ua, platform_for_ua, user_agents

CHROME = "141.0.1.2"


def test_user_agents_are_unique_chromium_desktop():
    uas = user_agents(CHROME)
    assert len(uas) == len(set(uas))
    assert len(uas) >= 2
    for ua in uas:
        assert f"Chrome/{CHROME}" in ua
        assert "Firefox" not in ua
        assert "Version/" not in ua
        assert "Windows NT 11." not in ua


def test_get_random_ua_uses_provided_chrome_version():
    ua = get_random_ua(CHROME)
    assert f"Chrome/{CHROME}" in ua
    assert ua in user_agents(CHROME)


def test_windows_ua_still_reports_nt_10():
    windows = [ua for ua in user_agents(CHROME) if "Windows" in ua]
    assert windows
    assert all("Windows NT 10.0" in ua for ua in windows)


def test_platform_hint_matches_os_in_ua():
    assert platform_for_ua("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/1") == '"Windows"'
    assert platform_for_ua(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/1"
    ) == '"macOS"'
    assert platform_for_ua("Mozilla/5.0 (X11; Linux x86_64) Chrome/1") == '"Linux"'


def test_fingerprint_is_de_with_english_fallback_and_matching_ch_platform():
    fp = build_fingerprint(CHROME)
    assert fp["locale"] == "de-DE"
    assert fp["timezone_id"] == "Europe/Berlin"
    assert fp["viewport"] == {"width": 1440, "height": 900}
    headers = fp["extra_http_headers"]
    assert headers["Accept-Language"].startswith("de-DE")
    assert "en-US" in headers["Accept-Language"]
    assert "en;" in headers["Accept-Language"]
    assert f"Chrome/{CHROME}" in fp["user_agent"]
    assert headers["Sec-CH-UA-Platform"] == platform_for_ua(fp["user_agent"])


def test_new_context_uses_launched_browser_version():
    async def _run():
        mgr = OptimizedPlaywrightManager(
            max_contexts=2, max_concurrent=1, recycle_every=100
        )
        fake_browser = MagicMock()
        fake_browser.version = CHROME
        fake_browser.new_context = AsyncMock(
            return_value=MagicMock(pages=[], browser=fake_browser)
        )
        fake_browser.close = AsyncMock()
        fake_pw = MagicMock()
        fake_pw.chromium.launch = AsyncMock(return_value=fake_browser)
        fake_pw.stop = AsyncMock()

        with patch("utils.browser.async_playwright") as ap:
            start_cm = AsyncMock()
            start_cm.start = AsyncMock(return_value=fake_pw)
            ap.return_value = start_cm
            await mgr.start()

        kwargs = fake_browser.new_context.await_args.kwargs
        assert f"Chrome/{CHROME}" in kwargs["user_agent"]
        assert kwargs["extra_http_headers"]["Sec-CH-UA-Platform"] == platform_for_ua(
            kwargs["user_agent"]
        )
        await mgr.close()

    asyncio.run(_run())
