import random

# Templates only — the Chrome build is filled from the launched Playwright
# Chromium (`browser.version`) so UA and Client Hints stay on the same version
# after a playwright upgrade.
#
# Windows 11 still advertises NT 10.0. Chrome on macOS still uses the frozen
# 10_15_7 token. Never put Firefox/Safari strings here: this process is Chromium.
_UA_TEMPLATES = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{build} Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{build} Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{build} Safari/537.36",
)

ACCEPT_LANGUAGE = "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"


def user_agents(chrome_version: str) -> list[str]:
    return [template.format(build=chrome_version) for template in _UA_TEMPLATES]


def get_random_ua(chrome_version: str) -> str:
    return random.choice(user_agents(chrome_version))


def platform_for_ua(ua: str) -> str:
    """Sec-CH-UA-Platform structured field matching the OS claimed in the UA."""
    if "Windows" in ua:
        return '"Windows"'
    if "Macintosh" in ua or "Mac OS" in ua:
        return '"macOS"'
    return '"Linux"'
