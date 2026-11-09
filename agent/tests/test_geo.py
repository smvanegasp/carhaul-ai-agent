"""Tests for city_to_zip — city required, state optional, typo-tolerant."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mia.geo import (
    CityToZipError,
    _names_match,
    canonicalize_state,
    city_to_zip,
)

HAS_API_KEY = bool(os.getenv("GOOGLE_MAPS_API_KEY", "").strip())
if not HAS_API_KEY:
    # Load from repo .env for local runs
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        HAS_API_KEY = bool(os.getenv("GOOGLE_MAPS_API_KEY", "").strip())
    except ImportError:
        pass

needs_api = pytest.mark.skipif(not HAS_API_KEY, reason="GOOGLE_MAPS_API_KEY not set")


class TestCanonicalizeState:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("MA", "MA"),
            ("ma", "MA"),
            ("Massachusetts", "MA"),
            ("massachusetts", "MA"),
            ("Massachusets", "MA"),  # typo
            ("Massachusettes", "MA"),  # typo
            ("FL", "FL"),
            ("Florida", "FL"),
            ("Florid", "FL"),  # minor typo
            ("Oregon", "OR"),
            ("Maine", "ME"),
            (None, None),
            ("", None),
            ("  ", None),
        ],
    )
    def test_resolves(self, raw, expected):
        assert canonicalize_state(raw) == expected

    def test_garbage_unrecognized(self):
        assert canonicalize_state("NotAState") is None

    def test_two_letter_no_fuzzy(self):
        # Must not fuzzy-collapse unrelated short codes
        assert canonicalize_state("XX") is None


class TestCityNameMatch:
    def test_exact(self):
        assert _names_match("Boston", "Boston")

    def test_typo(self):
        assert _names_match("Bostin", "Boston")
        assert _names_match("Bston", "Boston")

    def test_unrelated(self):
        assert not _names_match("Boston", "Miami")


class TestCityRequired:
    def test_empty_city_raises(self):
        with pytest.raises(CityToZipError) as exc:
            city_to_zip("")
        assert exc.value.code == "EMPTY_CITY"

    def test_whitespace_city_raises(self):
        with pytest.raises(CityToZipError) as exc:
            city_to_zip("   ")
        assert exc.value.code == "EMPTY_CITY"

    def test_unrecognized_state_raises(self):
        with pytest.raises(CityToZipError) as exc:
            city_to_zip("Boston", "NotAState")
        assert exc.value.code == "STATE_UNRECOGNIZED"


@needs_api
@pytest.mark.live
class TestLiveGeocoding:
    def test_city_only(self):
        result = city_to_zip("Portland")
        assert result["city"] == "Portland"
        assert result["state"] == "OR"
        assert result["state_name"] == "Oregon"
        assert result["zip"]

    def test_city_and_state_code(self):
        result = city_to_zip("Portland", "ME")
        assert result["state"] == "ME"
        assert result["zip"]

    def test_full_state_name(self):
        result = city_to_zip("Boston", "Massachusetts")
        assert result["city"] == "Boston"
        assert result["state"] == "MA"
        assert result["zip"]

    def test_state_typo(self):
        result = city_to_zip("Boston", "Massachusets")
        assert result["state"] == "MA"

    def test_city_typo(self):
        result = city_to_zip("Bostin", "MA")
        assert result["city"] == "Boston"
        assert result["state"] == "MA"

    def test_combined_city_state_string(self):
        result = city_to_zip("Boston, Massachusetts")
        assert result["city"] == "Boston"
        assert result["state"] == "MA"

    def test_nonexistent_city_state_raises(self):
        with pytest.raises(CityToZipError) as exc:
            city_to_zip("Boston", "FL")
        assert exc.value.code == "CITY_NOT_FOUND"
