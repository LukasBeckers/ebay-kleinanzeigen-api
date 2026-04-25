"""Parse the date strings kleinanzeigen.de prints on listing cards.

Card markup is ``<div class="aditem-main--top--right">…</div>`` with one of:

  * ``Heute, HH:MM``      — today at HH:MM (Europe/Berlin)
  * ``Gestern, HH:MM``    — yesterday at HH:MM (Europe/Berlin)
  * ``DD.MM.YYYY``        — older listings; no time of day, treat as midnight

Returns ISO-8601 strings in UTC so downstream consumers (proxy DB, hunter
JSONB columns) can compare timestamps directly.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

_TODAY_RE = re.compile(r"^\s*Heute\s*,\s*(\d{1,2}):(\d{2})\s*$")
_YESTERDAY_RE = re.compile(r"^\s*Gestern\s*,\s*(\d{1,2}):(\d{2})\s*$")
_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$")


def parse_listing_date(raw: str | None, *, now: datetime | None = None) -> str | None:
    """Convert a card-level date string to an ISO-8601 UTC timestamp.

    ``now`` is injectable so unit tests can pin "today"/"yesterday".
    Returns ``None`` for empty input or unrecognised formats.
    """
    if not raw:
        return None

    if now is None:
        now = datetime.now(BERLIN)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=BERLIN)

    if m := _TODAY_RE.match(raw):
        h, mi = int(m.group(1)), int(m.group(2))
        dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        return dt.astimezone(timezone.utc).isoformat()

    if m := _YESTERDAY_RE.match(raw):
        h, mi = int(m.group(1)), int(m.group(2))
        dt = (now - timedelta(days=1)).replace(hour=h, minute=mi, second=0, microsecond=0)
        return dt.astimezone(timezone.utc).isoformat()

    if m := _DATE_RE.match(raw):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d, 0, 0, 0, tzinfo=BERLIN)
        except ValueError:
            return None
        return dt.astimezone(timezone.utc).isoformat()

    return None
