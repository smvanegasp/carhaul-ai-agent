"""Accuracy suite for city_to_zip — major cities, STT typos, and negative cases.

Run:
  cd agent && uv run pytest -m live tests/test_geo_accuracy.py -v -s

Prints a pass/fail accuracy summary at the end.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from dotenv import load_dotenv

from mia.geo import CityToZipError, city_to_zip

ROOT = Path(__file__).resolve().parents[2]  # repo root, where .env lives
load_dotenv(ROOT / ".env")

HAS_API_KEY = bool(os.getenv("GOOGLE_MAPS_API_KEY", "").strip())
needs_api = pytest.mark.skipif(not HAS_API_KEY, reason="GOOGLE_MAPS_API_KEY not set")

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "major_city_zips.json"

# Every case calls Google (~100 paid requests): run only with `pytest -m live`.
pytestmark = pytest.mark.live


@dataclass(frozen=True)
class Case:
    label: str
    city: str
    state: str | None
    expected_zip: str | None = None  # set for success cases
    expect_error: bool = False
    kind: str = "clean"  # clean | city_typo | state_typo | both_typo | negative


def _load_fixture_zips() -> dict[tuple[str, str], str]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], str] = {}
    for row in rows:
        if "zip" in row:
            out[(row["city"], row["state"])] = row["zip"]
    return out


def _build_cases() -> list[Case]:
    zips = _load_fixture_zips()
    cases: list[Case] = []

    # --- Clean: all fixture cities (city + state code) ---
    for (city, state), zip_code in zips.items():
        cases.append(
            Case(
                label=f"clean:{city},{state}",
                city=city,
                state=state,
                expected_zip=zip_code,
                kind="clean",
            )
        )

    # --- STT-like city typos (phonetic / dropped letter — common ASR noise) ---
    city_typos = [
        ("New York", "NY", "New Yrok"),
        ("Los Angeles", "CA", "Los Angelos"),
        ("Chicago", "IL", "Chicargo"),
        ("Houston", "TX", "Huston"),
        ("Phoenix", "AZ", "Pheonix"),
        ("Philadelphia", "PA", "Philadelpha"),
        ("San Antonio", "TX", "San Antoneo"),
        ("San Diego", "CA", "San Dieago"),
        ("Dallas", "TX", "Dalles"),
        ("Austin", "TX", "Austan"),
        ("Seattle", "WA", "Seatle"),
        ("Denver", "CO", "Denvar"),
        ("Boston", "MA", "Bostin"),
        ("Miami", "FL", "Miammi"),
        ("Atlanta", "GA", "Atlana"),
        ("Albuquerque", "NM", "Albequerque"),
        ("Minneapolis", "MN", "Minneaplis"),
        ("New Orleans", "LA", "New Orleens"),
        ("Salt Lake City", "UT", "Salt Lake Citey"),
        ("San Francisco", "CA", "San Fransisco"),
    ]
    for city, state, spoken in city_typos:
        if (city, state) in zips:
            cases.append(
                Case(
                    label=f"city_typo:{spoken},{state}",
                    city=spoken,
                    state=state,
                    expected_zip=zips[(city, state)],
                    kind="city_typo",
                )
            )

    # --- STT-like state typos / full names ---
    state_typos = [
        ("Boston", "MA", "Massachusetts"),
        ("Boston", "MA", "Massachusets"),
        ("Los Angeles", "CA", "California"),
        ("Los Angeles", "CA", "Calfornia"),
        ("Chicago", "IL", "Illinois"),
        ("Chicago", "IL", "Illenois"),
        ("Miami", "FL", "Florida"),
        ("Miami", "FL", "Floridia"),
        ("Philadelphia", "PA", "Pennsylvania"),
        ("Philadelphia", "PA", "Pensylvania"),
        ("Atlanta", "GA", "Georgia"),
        ("Atlanta", "GA", "Georga"),
        ("Houston", "TX", "Texas"),
        ("Houston", "TX", "Texus"),
        ("Seattle", "WA", "Washington"),
        ("Portland", "OR", "Oregon"),
        ("Portland", "ME", "Maine"),
    ]
    for city, state, spoken_state in state_typos:
        if (city, state) in zips:
            cases.append(
                Case(
                    label=f"state_typo:{city},{spoken_state}",
                    city=city,
                    state=spoken_state,
                    expected_zip=zips[(city, state)],
                    kind="state_typo",
                )
            )

    # --- Both city + state slightly mangled ---
    both = [
        ("Boston", "MA", "Bostin", "Massachusets"),
        ("Chicago", "IL", "Chicargo", "Illenois"),
        ("Miami", "FL", "Miammi", "Floridia"),
        ("Seattle", "WA", "Seatle", "Washinton"),
        ("Phoenix", "AZ", "Pheonix", "Arizona"),
    ]
    for city, state, spoken_city, spoken_state in both:
        if (city, state) in zips:
            cases.append(
                Case(
                    label=f"both_typo:{spoken_city},{spoken_state}",
                    city=spoken_city,
                    state=spoken_state,
                    expected_zip=zips[(city, state)],
                    kind="both_typo",
                )
            )

    # --- Negatives: fake cities ---
    fake_cities = [
        ("Atlantis", "GA"),
        ("Narnia", "OR"),
        ("Wakanda", "CA"),
        ("Springfeldish", "OH"),
        ("Zzxq City", "TX"),
    ]
    for city, state in fake_cities:
        cases.append(
            Case(
                label=f"negative_fake:{city},{state}",
                city=city,
                state=state,
                expect_error=True,
                kind="negative",
            )
        )

    # --- Negatives: real city name, wrong state (must error, not invent a ZIP) ---
    wrong_state = [
        ("Boston", "FL"),
        ("Miami", "NY"),
        ("Seattle", "FL"),
        ("Chicago", "TX"),
        ("Portland", "FL"),
        ("Los Angeles", "NY"),
        ("Atlanta", "WA"),
        ("Denver", "FL"),
    ]
    for city, state in wrong_state:
        cases.append(
            Case(
                label=f"negative_wrong_state:{city},{state}",
                city=city,
                state=state,
                expect_error=True,
                kind="negative",
            )
        )

    return cases


CASES = _build_cases()
_RESULTS: list[tuple[Case, bool, str]] = []


@pytest.fixture(scope="session", autouse=True)
def _accuracy_summary():
    yield
    if not _RESULTS:
        return
    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    by_kind: dict[str, list[bool]] = {}
    for case, ok, _ in _RESULTS:
        by_kind.setdefault(case.kind, []).append(ok)

    lines = [
        "",
        "=" * 60,
        "city_to_zip accuracy summary",
        "=" * 60,
        f"Overall: {passed}/{total} ({100.0 * passed / total:.1f}%)",
    ]
    for kind, flags in sorted(by_kind.items()):
        k_pass = sum(flags)
        lines.append(f"  {kind:12} {k_pass}/{len(flags)} ({100.0 * k_pass / len(flags):.1f}%)")

    failures = [(c, detail) for c, ok, detail in _RESULTS if not ok]
    if failures:
        lines.append("Failures:")
        for case, detail in failures:
            lines.append(f"  - {case.label}: {detail}")
    lines.append("=" * 60)
    print("\n".join(lines))


@needs_api
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.label)
def test_accuracy_case(case: Case) -> None:
    try:
        result = city_to_zip(case.city, case.state)
    except CityToZipError as exc:
        ok = case.expect_error
        _RESULTS.append((case, ok, f"error:{exc.code}"))
        if not ok:
            pytest.fail(f"Unexpected error {exc.code}: {exc}")
        return

    if case.expect_error:
        _RESULTS.append((case, False, f"unexpected_success:zip={result.get('zip')}"))
        pytest.fail(f"Expected error, got {result}")

    got = result.get("zip")
    ok = got == case.expected_zip
    _RESULTS.append((case, ok, f"zip={got} expected={case.expected_zip}"))
    assert got == case.expected_zip, (
        f"{case.label}: expected ZIP {case.expected_zip}, got {got} ({result})"
    )
