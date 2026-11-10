"""Offline stand-in for mia.geo.city_to_zip (same return shape and error codes)."""

from __future__ import annotations

from typing import Any

from mia.geo import CityToZipError, canonicalize_state

CITIES = {
    "boston": ("Boston", "MA", "Massachusetts", "02110"),
    "bostin": ("Boston", "MA", "Massachusetts", "02110"),
    "san francisco": ("San Francisco", "CA", "California", "94103"),
    "sf": ("San Francisco", "CA", "California", "94103"),
    "new york": ("New York", "NY", "New York", "10001"),
    "portland": ("Portland", "OR", "Oregon", "97201"),
    "miami": ("Miami", "FL", "Florida", "33130"),
    "chicago": ("Chicago", "IL", "Illinois", "60601"),
}


def fake_city_to_zip(city: str, state: str | None = None, country: str = "US") -> dict[str, Any]:
    if not city or not city.strip():
        raise CityToZipError("EMPTY_CITY")
    if state and not canonicalize_state(state):
        raise CityToZipError("STATE_UNRECOGNIZED")
    if city.strip().lower() == "geofail":
        raise CityToZipError("GEOCODE_FAILED", "simulated outage")
    hit = CITIES.get(city.strip().lower())
    if not hit:
        raise CityToZipError("CITY_NOT_FOUND")
    name, code, full, zip_code = hit
    if state and canonicalize_state(state) != code:
        raise CityToZipError("STATE_MISMATCH")
    return {
        "city": name,
        "state": code,
        "state_name": full,
        "country": "US",
        "zip": zip_code,
        "formatted_address": f"{name}, {code} {zip_code}, USA",
        "lat": 0.0,
        "lng": 0.0,
    }
