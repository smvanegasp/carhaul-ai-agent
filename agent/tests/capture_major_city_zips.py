"""Capture representative ZIPs for major US cities via city_to_zip.

Not a test: run `uv run python tests/capture_major_city_zips.py` to refresh the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from mia.geo import CityToZipError, city_to_zip

ROOT = Path(__file__).resolve().parents[2]  # repo root, where .env lives
load_dotenv(ROOT / ".env")

# ~50 major US cities spanning many states (city, state_code)
CITIES = [
    ("New York", "NY"),
    ("Los Angeles", "CA"),
    ("Chicago", "IL"),
    ("Houston", "TX"),
    ("Phoenix", "AZ"),
    ("Philadelphia", "PA"),
    ("San Antonio", "TX"),
    ("San Diego", "CA"),
    ("Dallas", "TX"),
    ("San Jose", "CA"),
    ("Austin", "TX"),
    ("Jacksonville", "FL"),
    ("Fort Worth", "TX"),
    ("Columbus", "OH"),
    ("Charlotte", "NC"),
    ("Indianapolis", "IN"),
    ("San Francisco", "CA"),
    ("Seattle", "WA"),
    ("Denver", "CO"),
    ("Oklahoma City", "OK"),
    ("Nashville", "TN"),
    ("El Paso", "TX"),
    ("Washington", "DC"),
    ("Boston", "MA"),
    ("Las Vegas", "NV"),
    ("Portland", "OR"),
    ("Portland", "ME"),
    ("Detroit", "MI"),
    ("Memphis", "TN"),
    ("Louisville", "KY"),
    ("Baltimore", "MD"),
    ("Milwaukee", "WI"),
    ("Albuquerque", "NM"),
    ("Tucson", "AZ"),
    ("Fresno", "CA"),
    ("Sacramento", "CA"),
    ("Atlanta", "GA"),
    ("Miami", "FL"),
    ("Raleigh", "NC"),
    ("Omaha", "NE"),
    ("Minneapolis", "MN"),
    ("Tampa", "FL"),
    ("New Orleans", "LA"),
    ("Cleveland", "OH"),
    ("Honolulu", "HI"),
    ("Salt Lake City", "UT"),
    ("Birmingham", "AL"),
    ("Richmond", "VA"),
    ("Des Moines", "IA"),
    ("Boise", "ID"),
]

rows = []
for city, state in CITIES:
    try:
        r = city_to_zip(city, state)
        rows.append(
            {
                "city": city,
                "state": state,
                "zip": r["zip"],
                "formatted_address": r["formatted_address"],
                "resolved_city": r["city"],
                "resolved_state": r["state"],
            }
        )
        print(f"OK  {city}, {state} -> {r['zip']}")
    except CityToZipError as e:
        rows.append({"city": city, "state": state, "error": e.code, "message": str(e)})
        print(f"ERR {city}, {state} -> {e.code}")

out = Path(__file__).resolve().parent / "fixtures" / "major_city_zips.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
print(f"\nWrote {out} ({len(rows)} rows)")
