import random

# UAs must match the Chromium engine Playwright actually launches
# (the engine cross-checks the build number in navigator.userAgent), so keep
# the exact build of the installed chromium binary in every variant. Only the
# OS/viewport flavor varies.
_CHROME_BUILD = "139.0.7258.5"

_USER_AGENTS = [
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_CHROME_BUILD} Safari/537.36",
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_CHROME_BUILD} Safari/537.36",
    f"Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_CHROME_BUILD} Safari/537.36",
    f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_CHROME_BUILD} Safari/537.36",
    f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_CHROME_BUILD} Safari/537.36",
]


def get_random_ua():
    return random.choice(_USER_AGENTS)
