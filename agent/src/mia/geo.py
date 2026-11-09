"""City → ZIP for the car-haul voice agent.

City is required; state is optional (``MA`` / ``Massachusetts`` / minor typos).
Picks Google's best match so the agent can confirm the state aloud.
Raises ``CityToZipError`` on failure.
"""

from __future__ import annotations

import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

import googlemaps
from dotenv import load_dotenv

US_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

_STATE_CUTOFF = 0.78
_CITY_CUTOFF = 0.75
_CITY_TYPES = (
    "locality",
    "postal_town",
    "neighborhood",
    "sublocality",
    "sublocality_level_1",
    "administrative_area_level_3",
)


class CityToZipError(Exception):
    """Raised when a city cannot be resolved to a ZIP."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


@lru_cache(maxsize=1)
def _state_aliases() -> dict[str, str]:
    aliases = {code.lower(): code for code in US_STATE_NAMES}
    aliases.update({_norm(name): code for code, name in US_STATE_NAMES.items()})
    aliases.update({"washington dc": "DC", "wash dc": "DC"})
    return aliases


def canonicalize_state(state: str | None) -> str | None:
    """Map ``MA`` / ``Massachusetts`` / minor typos → 2-letter code."""
    if not state or not str(state).strip():
        return None
    norm = _norm(state)
    aliases = _state_aliases()
    if norm in aliases:
        return aliases[norm]
    if len(norm) <= 2:  # avoid fuzzy MI↔MN
        return None
    best, score = max(
        ((code, _similar(norm, name)) for name, code in aliases.items() if len(name) > 2),
        key=lambda item: item[1],
        default=(None, 0.0),
    )
    return best if score >= _STATE_CUTOFF else None


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _names_match(requested: str, resolved: str) -> bool:
    """True for exact/substring matches or small STT-like edits — not near-miss cities."""
    a, b = _norm(requested), _norm(resolved)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    sim = _similar(a, b)
    if sim < _CITY_CUTOFF:
        return False
    # Stricter edit budget for weaker similarity (blocks Atlantis→Atlanta, keeps Bostin).
    max_edits = 2 if sim >= 0.85 else 1
    return _levenshtein(a, b) <= max_edits


def _component(components: list[dict[str, Any]], *types: str, prefer: str = "short") -> str | None:
    for type_name in types:
        for c in components:
            if type_name in c.get("types", []):
                if prefer == "long":
                    return c.get("long_name") or c.get("short_name")
                return c.get("short_name") or c.get("long_name")
    return None


def _match_city(requested: str, components: list[dict[str, Any]]) -> str | None:
    """Return canonical city long_name if request fuzzy-matches long or short name."""
    for type_name in _CITY_TYPES:
        for c in components:
            if type_name not in c.get("types", []):
                continue
            long_name = c.get("long_name") or ""
            short_name = c.get("short_name") or ""
            if _names_match(requested, long_name) or _names_match(requested, short_name):
                return long_name or short_name
    return None


def _split_city_state(city: str, state: str | None) -> tuple[str, str | None]:
    if state and str(state).strip():
        return city.strip(), state.strip()
    if "," in city:
        left, right = (p.strip() for p in city.split(",", 1))
        if left and right and canonicalize_state(right):
            return left, right
    return city.strip(), None


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / ".env").exists() or (p / ".git").exists():
            return p
    return here


@lru_cache(maxsize=1)
def _client() -> googlemaps.Client:
    load_dotenv(_repo_root() / ".env")
    key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        raise CityToZipError(
            "MISSING_API_KEY",
            "GOOGLE_MAPS_API_KEY is missing in repo-root .env",
        )
    return googlemaps.Client(key=key)


def _postal_near(gmaps: googlemaps.Client, lat: float, lng: float) -> str | None:
    for kwargs in ({"result_type": ["postal_code"]}, {}):
        results = gmaps.reverse_geocode((lat, lng), **kwargs)
        if results:
            zip_code = _component(results[0].get("address_components", []), "postal_code")
            if zip_code:
                return zip_code
    return None


def city_to_zip(
    city: str,
    state: str | None = None,
    country: str = "US",
) -> dict[str, Any]:
    """Resolve a city to a representative ZIP.

    ``city`` is required. ``state`` is optional (code, full name, or minor typo).
    On success returns city/state/zip fields for spoken confirmation.
    On failure raises ``CityToZipError``.
    """
    city, state = _split_city_state(city or "", state)
    if not city:
        raise CityToZipError("EMPTY_CITY", "City is required")

    state_code = canonicalize_state(state) if state else None
    if state and not state_code:
        raise CityToZipError("STATE_UNRECOGNIZED", f"Unrecognized state: {state!r}")

    state_label = US_STATE_NAMES[state_code] if state_code else None
    address = ", ".join(p for p in (city, state_label or state_code, country) if p)
    components: dict[str, str] = {"country": country}
    if state_code:
        components["administrative_area"] = state_code

    gmaps = _client()
    try:
        results = gmaps.geocode(address, components=components)
    except CityToZipError:
        raise
    except Exception as exc:
        raise CityToZipError("GEOCODE_FAILED", str(exc)) from exc

    if not results:
        raise CityToZipError("ZERO_RESULTS", f"No results for {address!r}")

    best = results[0]
    comps = best.get("address_components", [])
    loc = best["geometry"]["location"]
    lat, lng = float(loc["lat"]), float(loc["lng"])
    types = set(best.get("types") or [])
    resolved_city = _match_city(city, comps)
    resolved_state = _component(comps, "administrative_area_level_1")

    if not (types & set(_CITY_TYPES)) or not resolved_city:
        raise CityToZipError("CITY_NOT_FOUND", f"Could not resolve city {city!r}")

    if state_code and resolved_state and resolved_state.upper() != state_code:
        raise CityToZipError(
            "STATE_MISMATCH",
            f"Expected {state_code}, got {resolved_state}",
        )

    zip_code = _component(comps, "postal_code") or _postal_near(gmaps, lat, lng)
    if not zip_code:
        raise CityToZipError("NO_POSTAL_CODE", f"No ZIP for {best.get('formatted_address')!r}")

    out_state = resolved_state or state_code
    return {
        "city": resolved_city,
        "state": out_state,
        "state_name": US_STATE_NAMES.get((out_state or "").upper()),
        "country": country,
        "zip": zip_code,
        "formatted_address": best.get("formatted_address"),
        "lat": lat,
        "lng": lng,
    }
