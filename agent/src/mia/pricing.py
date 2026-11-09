"""Quote every vehicle and build what Mia says about it.

Prices and the spoken summary are computed here, never by the LLM: the model only reads
``QuoteSummary.speech`` back. Naming rules from docs/CONVERSATION_DESIGN.md: each car gets the
shortest name that tells it apart from the others (make → make + model → year + make + model),
and identical cars are grouped ("the two 2020 Toyota Corollas").
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from mia.carhauler import CarHaulerClient, Quote

MULTI_VEHICLE_LINE = (
    "You can discuss potential discounts for multiple vehicles with a licensed representative."
)

_COUNT_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


@dataclass(frozen=True)
class QuoteRequest:
    """One vehicle to quote. Either ``trim_id`` (precise) or ``vehicle_type`` (fallback)."""

    from_zip: str
    to_zip: str
    trim_id: int | None = None
    vehicle_type: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    operational: bool = True
    quote_id: str | None = None


@dataclass(frozen=True)
class VehicleQuote:
    request: QuoteRequest
    quote: Quote

    @property
    def price(self) -> int:
        return self.quote.price


@dataclass(frozen=True)
class QuoteSummary:
    total: int
    items: list[tuple[str, int]]  # (spoken label, price) after grouping identical cars
    vehicles: list[VehicleQuote]
    speech: str
    transit_days: tuple[int, int] | None


def usd(amount: int) -> str:
    return f"${amount:,}"


def _join(parts: Sequence[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _plural(name: str) -> str:
    return name if name.endswith("s") else name + "s"


def _keys(r: QuoteRequest) -> list[tuple]:
    """Ever more specific identities: make (or type), make + model, year + make + model."""
    base = r.make or r.vehicle_type or "vehicle"
    return [
        (base,),
        (base, r.model),
        (r.year, base, r.model),
    ]


def _name(r: QuoteRequest, level: int) -> str:
    if not r.make:  # only the body type is known ("the SUV", "the pickup")
        return "SUV" if r.vehicle_type == "suv" else (r.vehicle_type or "vehicle")
    parts = {
        0: [r.make],
        1: [r.make, r.model],
        2: [str(r.year) if r.year else None, r.make, r.model],
    }[level]
    return " ".join(p for p in parts if p)


def vehicle_labels(requests: Sequence[QuoteRequest]) -> list[tuple[str, list[int]]]:
    """Group vehicles and name each group. Returns [(label, [indexes])] in first-seen order.

    >>> # Honda Civic + Toyota 4Runner + Toyota Corolla →
    >>> # ["the Honda", "the Toyota 4Runner", "the Toyota Corolla"]
    """
    groups: list[tuple[str, list[int]]] = []
    seen: set[int] = set()
    all_keys = [_keys(r) for r in requests]
    for i, r in enumerate(requests):
        if i in seen:
            continue
        for level in range(3):
            twins = [j for j, k in enumerate(all_keys) if k[level] == all_keys[i][level]]
            if len(twins) == 1:
                groups.append((f"the {_name(r, level)}", [i]))
                seen.add(i)
                break
        else:
            # Same year, make and model: say them together.
            twins = [j for j, k in enumerate(all_keys) if k[2] == all_keys[i][2]]
            seen.update(twins)
            count = _COUNT_WORDS.get(len(twins), str(len(twins)))
            groups.append((f"the {count} {_plural(_name(r, 2))}", twins))
    return groups


# --- transit time ------------------------------------------------------------------------

_UNIT_HOURS = {"day": 24.0, "hour": 1.0, "minute": 1 / 60}


def driving_hours(driving_time: str) -> float | None:
    """'5 days and 2 hours drive' → 122.0. None if nothing parsable."""
    total, found = 0.0, False
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(day|hour|minute)s?", driving_time.lower()):
        total += float(amount) * _UNIT_HOURS[unit]
        found = True
    return total if found else None


def transit_days(driving_time: str) -> tuple[int, int] | None:
    """Door to door: the driving time plus 0–3 days for loading and unloading, in whole days.

    '5 days and 2 hours drive' → (6, 9).
    """
    hours = driving_hours(driving_time)
    if hours is None:
        return None
    days = hours / 24
    return max(1, math.ceil(days)), math.ceil(days + 3)


# --- quoting -----------------------------------------------------------------------------


async def quote_vehicles(
    client: CarHaulerClient,
    requests: Sequence[QuoteRequest],
    shipping_date: date | None = None,
) -> list[VehicleQuote]:
    """Quote each vehicle, one request at a time (the quote endpoint has a burst limit).

    Identical requests (same route, trim/type and condition) are quoted once.
    """
    cache: dict[tuple, Quote] = {}
    out: list[VehicleQuote] = []
    for r in requests:
        key = (r.from_zip, r.to_zip, r.trim_id, r.vehicle_type, r.operational)
        if key not in cache:
            cache[key] = await client.quote(
                r.from_zip,
                r.to_zip,
                trim_id=r.trim_id,
                vehicle_type=None if r.trim_id else r.vehicle_type,
                operational=r.operational,
                shipping_date=shipping_date,
            )
        out.append(VehicleQuote(r, cache[key]))
    return out


def summarize(quotes: Sequence[VehicleQuote]) -> QuoteSummary:
    if not quotes:
        raise ValueError("no quotes to summarize")
    requests = [q.request for q in quotes]
    total = sum(q.price for q in quotes)
    items: list[tuple[str, int]] = []
    phrases: list[str] = []
    for label, idx in vehicle_labels(requests):
        prices = [quotes[i].price for i in idx]
        group_total = sum(prices)
        items.append((label, group_total))
        if len(idx) > 1 and len(set(prices)) == 1:
            phrases.append(f"{usd(prices[0])} each for {label}")
        else:
            phrases.append(f"{usd(group_total)} for {label}")

    speech = f"Your estimated cost is {usd(total)}."
    if len(quotes) > 1:
        speech += f" It would be {_join(phrases)}."
        routes = {(r.from_zip, r.to_zip) for r in requests}
        if len(routes) < len(requests):  # at least two vehicles share a route
            speech += " " + MULTI_VEHICLE_LINE

    spans = [d for d in (transit_days(q.quote.driving_time) for q in quotes) if d]
    transit = (min(s[0] for s in spans), max(s[1] for s in spans)) if spans else None
    return QuoteSummary(
        total=total, items=items, vehicles=list(quotes), speech=speech, transit_days=transit
    )
