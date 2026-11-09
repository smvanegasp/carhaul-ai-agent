from __future__ import annotations

import pytest

from mia.pricing import (
    MULTI_VEHICLE_LINE,
    QuoteRequest,
    driving_hours,
    quote_vehicles,
    summarize,
    transit_days,
    vehicle_labels,
)

BOS, SF = "02110", "94103"


def req(year, make, model, trim=None, **kw) -> QuoteRequest:
    return QuoteRequest(BOS, SF, trim_id=trim, year=year, make=make, model=model, **kw)


def labels(*requests) -> list[str]:
    return [label for label, _ in vehicle_labels(requests)]


# --- naming rules ------------------------------------------------------------------------


def test_one_vehicle_is_named_by_make():
    assert labels(req(2025, "Honda", "Civic")) == ["the Honda"]


def test_different_makes_use_make_only():
    assert labels(req(2025, "Honda", "Civic"), req(2020, "Toyota", "4Runner")) == [
        "the Honda",
        "the Toyota",
    ]


def test_same_make_different_models_use_make_and_model():
    assert labels(
        req(2025, "Honda", "Civic"), req(2020, "Toyota", "4Runner"), req(2019, "Toyota", "Corolla")
    ) == ["the Honda", "the Toyota 4Runner", "the Toyota Corolla"]


def test_same_model_different_years_use_year_make_model():
    assert labels(req(2025, "Honda", "Civic"), req(2018, "Honda", "Civic")) == [
        "the 2025 Honda Civic",
        "the 2018 Honda Civic",
    ]


def test_identical_vehicles_are_grouped():
    groups = vehicle_labels(
        [
            req(2020, "Toyota", "Corolla"),
            req(2025, "Honda", "Civic"),
            req(2020, "Toyota", "Corolla"),
        ]
    )
    assert groups == [("the two 2020 Toyota Corollas", [0, 2]), ("the Honda", [1])]


def test_type_only_vehicles():
    assert labels(QuoteRequest(BOS, SF, vehicle_type="suv"), req(2025, "Honda", "Civic")) == [
        "the SUV",
        "the Honda",
    ]


# --- transit time -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, hours, days",
    [
        ("5 days and 2 hours drive", 122, (6, 9)),
        ("1 day and 7 hours drive", 31, (2, 5)),
        ("18 hours drive", 18, (1, 4)),
        ("3 days drive", 72, (3, 6)),
        ("45 minutes drive", 0.75, (1, 4)),
    ],
)
def test_transit(text, hours, days):
    assert driving_hours(text) == pytest.approx(hours)
    assert transit_days(text) == days


def test_transit_unparsable():
    assert transit_days("soon") is None


# --- quoting and the spoken summary (reference conversations) -----------------------------


async def test_one_vehicle(client):
    quotes = await quote_vehicles(client, [req(2025, "Honda", "Civic", trim=34547)])
    s = summarize(quotes)
    assert s.total == 1291
    assert s.speech == "Your estimated cost is $1,291."
    assert MULTI_VEHICLE_LINE not in s.speech
    assert s.transit_days == (6, 9)


async def test_two_vehicles(client):
    quotes = await quote_vehicles(
        client,
        [req(2025, "Honda", "Civic", trim=34547), req(2020, "Toyota", "4Runner", trim=75020)],
    )
    s = summarize(quotes)
    assert s.total == 1291 + quotes[1].price
    assert s.speech == (
        f"Your estimated cost is ${s.total:,}. It would be $1,291 for the Honda and "
        f"${quotes[1].price:,} for the Toyota. {MULTI_VEHICLE_LINE}"
    )


async def test_three_vehicles_total_is_the_sum(client):
    quotes = await quote_vehicles(
        client,
        [
            req(2025, "Honda", "Civic", trim=34547),
            req(2020, "Toyota", "4Runner", trim=75020),
            req(2019, "Toyota", "Corolla", trim=75119),
        ],
    )
    s = summarize(quotes)
    assert s.total == sum(q.price for q in quotes)
    assert "for the Honda, " in s.speech
    assert "for the Toyota 4Runner and " in s.speech
    assert "for the Toyota Corolla." in s.speech


async def test_identical_vehicles_quoted_once_and_said_each(client, fake_api):
    quotes = await quote_vehicles(
        client,
        [req(2020, "Toyota", "Corolla", trim=75120), req(2020, "Toyota", "Corolla", trim=75120)],
    )
    assert fake_api.calls["/quote"] == 1
    s = summarize(quotes)
    price = quotes[0].price
    assert s.total == 2 * price
    assert f"${price:,} each for the two 2020 Toyota Corollas" in s.speech


async def test_different_routes_skip_the_multi_vehicle_line(client):
    quotes = await quote_vehicles(
        client,
        [
            req(2025, "Honda", "Civic", trim=34547),
            QuoteRequest("10001", SF, trim_id=75020, year=2020, make="Toyota", model="4Runner"),
        ],
    )
    assert MULTI_VEHICLE_LINE not in summarize(quotes).speech


async def test_vehicle_type_fallback_is_quoted_by_type(client):
    quotes = await quote_vehicles(client, [QuoteRequest(BOS, SF, vehicle_type="suv")])
    assert quotes[0].price == 1338


def test_summarize_needs_quotes():
    with pytest.raises(ValueError):
        summarize([])
