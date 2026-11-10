"""Stage 8: the error matrix. For every error a tool can hit, what Mia is told to do (`next`)
and whether it counts as escalated (a transfer after it is a "forced" one).

Two kinds (docs/CONVERSATION_DESIGN.md): a detail we couldn't find -> ask again (the third time
in a row -> offer a licensed representative); a service failure (Google Maps down, CarHauler
401/402/5xx/rate limit after retries) -> apologize and offer a representative right away.
"""

from __future__ import annotations

import httpx
import pytest
from fake_geo import fake_city_to_zip

from mia import tools
from mia.state import QuoteSession
from mia.tools import ESCALATE, STILL_NOT_FOUND, Services

ROUTE = "Boston, Massachusetts to San Francisco, California"


@pytest.fixture
def state():
    return QuoteSession()


@pytest.fixture
def services(client, resolver):
    return Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)


async def _route(state, services, origin="Boston", said=ROUTE):
    return await tools.save_origin_destination(
        state, services, origin_city=origin, destination_city="San Francisco", said=said
    )


# --- route ---------------------------------------------------------------------------------


async def test_city_not_found_asks_again(state, services):
    r = await _route(state, services, origin="Atlantis", said="From Atlantis to San Francisco")
    assert r["error_code"] == "CITY_NOT_FOUND" and "couldn't find Atlantis" in r["next"]
    assert not state.escalated
    assert state.destination is not None  # the side that worked is kept


async def test_state_mismatch_asks_to_confirm(state, services):
    said = "From Boston, Texas to San Francisco"
    r = await tools.save_origin_destination(
        state,
        services,
        origin_city="Boston",
        origin_state="TX",
        destination_city="San Francisco",
        said=said,
    )
    assert r["error_code"] == "STATE_MISMATCH" and "confirm the city and the state" in r["next"]


async def test_maps_down_escalates_right_away(state, services):
    r = await _route(state, services, origin="Geofail", said="From Geofail to San Francisco")
    assert r["error_code"] == "GEOCODING_UNAVAILABLE" and r["next"] == ESCALATE
    assert state.escalated


async def test_the_third_city_not_found_in_a_row_offers_a_person(state, services):
    said = "From Atlantis to San Francisco"
    for attempt in (1, 2):
        r = await _route(state, services, origin="Atlantis", said=said)
        assert r["next"] != STILL_NOT_FOUND and r["attempts"] == attempt
    r = await _route(state, services, origin="Atlantis", said=said)
    assert r["next"] == STILL_NOT_FOUND and state.escalated


async def test_a_success_resets_the_count(state, services):
    said = "From Atlantis to San Francisco. Sorry, Boston"
    await _route(state, services, origin="Atlantis", said=said)
    await _route(state, services, origin="Atlantis", said=said)
    assert (await _route(state, services, said=said))["ok"]
    r = await _route(state, services, origin="Atlantis", said=said)
    assert r["attempts"] == 1 and r["next"] != STILL_NOT_FOUND


# --- vehicles ------------------------------------------------------------------------------


async def test_make_not_found_asks_again_then_offers_a_person(state, services):
    said = "It's a 2020 Zorgmobile"
    for attempt in (1, 2, 3):
        r = await tools.save_vehicle(state, services, year=2020, make="Zorgmobile", said=said)
        assert r["error_code"] == "MAKE_NOT_FOUND" and r["attempts"] == attempt
    assert r["next"] == STILL_NOT_FOUND and state.escalated


async def test_missing_details_are_questions_not_failures(state, services):
    said = "It's a Honda"
    for _ in range(4):
        r = await tools.save_vehicle(state, services, make="Honda", said=said)
        assert r["error_code"] == "MISSING_MODEL" and r["next"] != STILL_NOT_FOUND
    assert not state.escalated


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": "Missing or invalid API key."}),
        httpx.Response(402, json={"error": "Free tier exhausted"}),
        httpx.Response(503),
    ],
    ids=["401", "402", "503"],
)
async def test_carhauler_failures_escalate(state, services, fake_api, response):
    await _route(state, services)
    fake_api.fail_next(*[response] * 6)  # outlasts the retries
    r = await tools.save_vehicle(
        state, services, year=2025, make="Honda", model="Civic", said="It's a 2025 Honda Civic"
    )
    assert r["ok"] is False and r["next"] == ESCALATE and state.escalated


# --- quote ---------------------------------------------------------------------------------


async def _ready(state, services):
    await _route(state, services)
    await tools.save_vehicle(
        state, services, year=2025, make="Honda", model="Civic", said="It's a 2025 Honda Civic"
    )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(402, json={"error": "Free tier exhausted"}),
        httpx.Response(200, json={"success": False, "message": "Too many requests, slow down"}),
        httpx.Response(500),
    ],
    ids=["402", "rate-limited", "500"],
)
async def test_quote_failures_escalate_and_never_invent_a_price(
    state, services, fake_api, response
):
    await _ready(state, services)
    fake_api.fail_next(*[response] * 6)
    r = await tools.get_quote(state, services)
    assert r["ok"] is False and r["next"] == ESCALATE and "say" not in r
    assert state.quote is None and state.escalated


async def test_a_bad_zip_at_quote_time_asks_for_the_city(state, services, fake_api):
    await _ready(state, services)
    fake_api.fail_next(
        httpx.Response(200, json={"success": False, "message": "Invalid origin ZIP code"})
    )
    r = await tools.get_quote(state, services)
    assert r["error_code"] == "INVALID_ORIGIN_ZIP" and "pickup city" in r["next"]
    assert not state.escalated


async def test_a_forced_transfer_follows_an_escalation(state, services, fake_api):
    await _ready(state, services)
    fake_api.fail_next(*[httpx.Response(402)] * 6)
    await tools.get_quote(state, services)
    await tools.request_human(state, services, asked=False)
    assert state.transfer_kind == "forced"


# --- off-topic -----------------------------------------------------------------------------


async def test_off_topic_steers_back_twice_then_ends(state, services):
    for n in (1, 2):
        r = await tools.note_off_topic(state, services)
        assert r["off_topic"] == n and "steer back" in r["next"] and not state.ended
    r = await tools.note_off_topic(state, services)
    assert state.ended and state.end_reason == "off_topic" and state.hang_up_after_speech
    assert "Don't transfer" in r["next"]
