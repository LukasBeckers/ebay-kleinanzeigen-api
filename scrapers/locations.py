"""Parse the location string kleinanzeigen.de prints on listing cards.

Card markup is ``<div class="aditem-main--top--left">…</div>`` with one of:

  * ``"52249 Eschweiler (28 km)"``     — typical: PLZ + city + km
  * ``"44809 Bochum-Mitte (ca. 100 km)"`` — boundary case has the ``ca.`` prefix
  * ``"50858 Junkersdorf (60 km)"``    — district name without "City" suffix
  * ``"Gangelt"``                      — same town as user → no PLZ, no km
  * ``"55411 Bingen"``                 — nationwide-recommendation cards in
                                         the silent-fallback response shape

Returns ``(location_zip, location_city, distance_km)``.  Each is ``None``
when not present in the input.  ``distance_km`` is an int (we never need
sub-km precision; kleinanzeigen rounds to whole km already).
"""
from __future__ import annotations

import re

# Typical form: "<plz?> <city?> (<ca.?> <km> km)?".  The PLZ is 4–5 digits;
# the city is everything between the PLZ and the parenthesised distance;
# the distance segment is optional (same-town cards omit it entirely).
_PLZ_RE = re.compile(r"^\s*(\d{4,5})\s+(.+?)\s*$")
_KM_RE = re.compile(r"\(\s*(?:ca\.\s*)?(\d+)\s*km\s*\)\s*$")


def parse_location(raw: str | None) -> tuple[str | None, str | None, int | None]:
    """Split a card-level location string into (zip, city, distance_km).

    Each component is independently optional; missing pieces return ``None``.
    The function never raises — kleinanzeigen layouts vary by category.
    """
    if not raw:
        return (None, None, None)
    s = raw.strip()
    # Pull the trailing "(N km)" segment first so the rest is just the
    # PLZ + city.  Note: lowercase the haystack for matching but keep the
    # original casing for the city.
    distance_km: int | None = None
    m = _KM_RE.search(s)
    if m:
        try:
            distance_km = int(m.group(1))
        except ValueError:
            pass
        s = s[: m.start()].rstrip()

    plz: str | None = None
    city: str | None = None
    pm = _PLZ_RE.match(s)
    if pm:
        plz = pm.group(1).strip()
        city = pm.group(2).strip() or None
    elif s:
        # No PLZ — bare city name (same town as searcher).
        city = s

    return (plz, city, distance_km)
