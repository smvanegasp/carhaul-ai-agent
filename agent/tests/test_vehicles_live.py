"""Accuracy suite for vehicle resolution against the real CarHauler247 catalog.

Run:
  cd agent && uv run pytest -m live tests/test_vehicles_live.py -v -s

Catalog lookups cost ~$0.0001 each after the free tier and are cached per run (~80 calls). One
real quote at the end (the reference Boston → San Francisco Civic). Prints a pass-rate summary
by case kind.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from mia.carhauler import CarHaulerClient
from mia.pricing import QuoteRequest, quote_vehicles, summarize
from mia.vehicles import VehicleError, VehicleErrorCode, VehicleResolver

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
HAS_KEY = bool(os.getenv("CARHAULER_API_KEY") or os.getenv("CARHAULER_API_KEY_QA"))
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not HAS_KEY, reason="CARHAULER_API_KEY(_QA) not set"),
]


@dataclass(frozen=True)
class Case:
    kind: str  # clean | spoken | typo | no_make | negative
    year: int | None
    make: str | None
    model: str | None
    expect: str | VehicleErrorCode  # "Make Model" or the error code


CASES = [
    # Clean
    Case("clean", 2025, "Honda", "Civic", "Honda Civic"),
    Case("clean", 2020, "Toyota", "4Runner", "Toyota 4Runner"),
    Case("clean", 2019, "Toyota", "Corolla", "Toyota Corolla"),
    Case("clean", 2022, "Ford", "F-150", "Ford F-150"),
    Case("clean", 2018, "Jeep", "Wrangler", "Jeep Wrangler"),
    Case("clean", 2023, "Toyota", "RAV4", "Toyota RAV4"),
    Case("clean", 2017, "Honda", "CR-V", "Honda CR-V"),
    Case("clean", 2020, "Tesla", "Model 3", "Tesla Model 3"),
    Case("clean", 2020, "Subaru", "Outback", "Subaru Outback"),
    Case("clean", 2019, "Nissan", "Altima", "Nissan Altima"),
    Case("clean", 2021, "Hyundai", "Elantra", "Hyundai Elantra"),
    Case("clean", 2016, "Mazda", "CX-5", "Mazda CX-5"),
    Case("clean", 2022, "BMW", "X5", "BMW X5"),
    Case("clean", 2021, "Audi", "A4", "Audi A4"),
    # Spoken forms (what speech-to-text gives us)
    Case("spoken", 2020, "Toyota", "four runner", "Toyota 4Runner"),
    Case("spoken", 2017, "Honda", "CRV", "Honda CR-V"),
    Case("spoken", 2022, "Ford", "F150", "Ford F-150"),
    Case("spoken", 2020, "Tesla", "model three", "Tesla Model 3"),
    Case("spoken", 2023, "Toyota", "rav four", "Toyota RAV4"),
    Case("spoken", 2016, "Mazda", "CX five", "Mazda CX-5"),
    Case("spoken", 2019, "VW", "Jetta", "Volkswagen Jetta"),
    Case("spoken", 2020, "Chevy", "Malibu", "Chevrolet Malibu"),
    Case("spoken", 2025, "honda", "civic sedan", "Honda Civic"),
    # Typos
    Case("typo", 2021, "Hundai", "Elantra", "Hyundai Elantra"),
    Case("typo", 2020, "Toyta", "Camry", "Toyota Camry"),
    Case("typo", 2019, "Nisan", "Altima", "Nissan Altima"),
    Case("typo", 2019, "Toyota", "Corola", "Toyota Corolla"),
    Case("typo", 2020, "Subaru", "Outbak", "Subaru Outback"),
    Case("typo", 2018, "Jep", "Wrangler", "Jeep Wrangler"),
    # Model only ("4Runner from 2020")
    Case("no_make", 2020, None, "4Runner", "Toyota 4Runner"),
    Case("no_make", 2025, None, "Civic", "Honda Civic"),
    Case("no_make", 2018, None, "Wrangler", "Jeep Wrangler"),
    Case("no_make", 2020, None, "Outback", "Subaru Outback"),
    Case("no_make", 2019, None, "Camry", "Toyota Camry"),
    # Must not resolve
    Case("negative", 2020, "Toyota", None, VehicleErrorCode.MISSING_MODEL),
    Case("negative", None, "Toyota", "4Runner", VehicleErrorCode.MISSING_YEAR),
    Case("negative", 2020, "Honda", "Spaceship", VehicleErrorCode.MODEL_NOT_FOUND),
    Case("negative", 2020, "Atlantis Motors", "Civic", VehicleErrorCode.MAKE_NOT_FOUND),
    Case("negative", 1950, "Honda", "Civic", VehicleErrorCode.YEAR_NOT_AVAILABLE),
    Case("negative", 2020, None, None, VehicleErrorCode.MISSING_MAKE_AND_MODEL),
]

RESULTS: dict[str, list[bool]] = defaultdict(list)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def resolver():
    client = CarHaulerClient()
    yield VehicleResolver(client)
    await client.aclose()


@pytest.fixture(scope="module", autouse=True)
def report():
    yield
    print("\n\nVehicle resolution accuracy")
    total_ok = total = 0
    for kind, oks in RESULTS.items():
        print(f"  {kind:<9} {sum(oks):>3}/{len(oks):<3}")
        total_ok, total = total_ok + sum(oks), total + len(oks)
    if total:
        print(f"  {'overall':<9} {total_ok:>3}/{total:<3} ({100 * total_ok / total:.0f}%)")


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.kind}:{c.year} {c.make} {c.model}")
async def test_resolve(resolver, case):
    ok = False
    try:
        try:
            v = await resolver.resolve(year=case.year, make=case.make, model=case.model)
            got = f"{v.make} {v.model}"
        except VehicleError as exc:
            got = exc.code
        ok = got == case.expect
        assert got == case.expect
    finally:
        RESULTS[case.kind].append(ok)


@pytest.mark.asyncio(loop_scope="module")
async def test_reference_quote(resolver):
    """happy_path_ngc_1v: a 2025 Honda Civic, Boston 02110 → San Francisco 94103."""
    v = await resolver.resolve(year=2025, make="Honda", model="Civic")
    client = resolver._client
    quotes = await quote_vehicles(
        client,
        [QuoteRequest("02110", "94103", trim_id=v.trim_id, year=2025, make="Honda", model="Civic")],
    )
    s = summarize(quotes)
    print(f"\n  {v.label} ({v.trim_name}): {s.speech} Transit {s.transit_days} days.")
    assert 300 < s.total < 5000
    assert quotes[0].quote.distance > 2500
