"""A small in-memory CarHauler247 API for offline tests (served through respx).

Shapes match the real API (see mia/carhauler.py). Quote failures come back as HTTP 200 with
success:false, like the real thing; tests can queue failures with ``fail_next``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import httpx

BASE = "https://carhauler.test/api/public/v2"

MAKES = {
    23: "Honda",
    63: "Toyota",
    9: "Chevrolet",
    41: "Mercedes-Benz",
    4: "Audi",
    18: "Ford",
    22: "GMC",
    59: "SRT",  # has no models: the real API answers with an HTML error page
}

MODELS: dict[int, dict[int, str]] = {
    23: {681: "Civic", 682: "Accord", 678: "CR-V", 1672: "Civic del Sol"},
    63: {
        750: "4Runner",
        751: "Corolla",
        752: "Corolla Cross",
        753: "Camry",
        754: "Camry Hybrid",
        755: "RAV4",
    },
    9: {900: "Silverado 1500", 901: "Silverado 2500HD", 902: "Malibu"},
    41: {950: "C-Class"},
    4: {48: "A4", 49: "A5"},
    18: {960: "F-150", 961: "Ranger"},
    22: {970: "Sierra 1500", 971: "Canyon", 972: "Ranger"},  # fake: a model name two makes share
}

DEFAULT_YEARS = list(range(2025, 2014, -1))
YEARS = {681: list(range(2025, 1972, -1))}  # the Civic goes back to 1973

# Real trims for the 2025 Civic (base trim first, as the API returns them).
TRIMS = {
    (681, 2025): [
        {"id": 34547, "name": "LX 4dr Sedan (2.0L 4cyl CVT)"},
        {"id": 34551, "name": "Si 4dr Sedan (1.5L 4cyl Turbo 6M)"},
    ],
    (681, 2015): [],  # a year listed without trims
}

PRICES = {34547: 1291}  # trimId → price; others get a price derived from the ID
TYPE_PRICES = {"sedan": 1268, "suv": 1338, "pickup": 1450}


def trim_id(model_id: int, year: int) -> int:
    return model_id * 100 + year % 100


def price_for(trim: int | None, vehicle_type: str | None) -> int:
    if trim is not None:
        return PRICES.get(trim, 1000 + trim % 500)
    return TYPE_PRICES.get(vehicle_type or "sedan", 1268)


class FakeCarHauler:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.queued: list[httpx.Response | Exception] = []
        self.requests: list[httpx.Request] = []

    def fail_next(self, *responses: httpx.Response | Exception) -> None:
        self.queued.extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/public/v2")
        self.calls[path] += 1
        self.requests.append(request)
        if self.queued:
            nxt = self.queued.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        if request.headers.get("authorization") != "Bearer test-key":
            return httpx.Response(401, json={"error": "Missing or invalid API key."})
        p = request.url.params
        if path == "/car/makes":
            return httpx.Response(200, json=[{"id": i, "name": n} for i, n in MAKES.items()])
        if path == "/car/models":
            if p["makeId"] == "59":
                return httpx.Response(200, text="<!DOCTYPE html><title>Car shipping error.</title>")
            models = MODELS.get(int(p["makeId"]), {})
            return httpx.Response(200, json=[{"id": i, "name": n} for i, n in models.items()])
        if path == "/car/years":
            return httpx.Response(200, json=YEARS.get(int(p["modelId"]), DEFAULT_YEARS))
        if path == "/car/trims":
            model_id, year = int(p["modelId"]), int(p["year"])
            if (model_id, year) in TRIMS:
                return httpx.Response(200, json=TRIMS[(model_id, year)])
            return httpx.Response(
                200, json=[{"id": trim_id(model_id, year), "name": "Base 4dr Sedan"}]
            )
        if path == "/quote":
            return self._quote(p)
        return httpx.Response(404, json={"error": "not found"})

    def _quote(self, p: httpx.QueryParams) -> httpx.Response:
        def fail(message: str) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "message": message})

        if p["fromZip"] == p["toZip"]:
            return fail("Origin and destination ZIP codes cannot be the same")
        if p["fromZip"] == "00000":
            return fail("Invalid origin ZIP code: 0")
        trim = int(p["trimId"]) if "trimId" in p else None
        if trim == 999:
            return fail(f"Invalid trim ID: {trim}")
        vtype = p.get("vehicleType")
        body: dict[str, Any] = {
            "success": True,
            "quote": {
                "price": price_for(trim, vtype),
                "distance": 3095,
                "drivingTime": "5 days and 2 hours drive",
                "vehicleType": vtype or "sedan",
                "carrier": "open",
                "operational": p.get("isOperational", "true") == "true",
            },
        }
        return httpx.Response(200, json=body)


RATE_LIMITED = httpx.Response(
    200,
    json={"success": False, "message": "Too many requests. Please wait a moment and try again."},
)
