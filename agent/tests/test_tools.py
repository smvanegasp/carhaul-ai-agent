"""Tool behavior without an LLM: state changes, error codes and the `next` guidance."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fake_geo import fake_city_to_zip

from mia import tools
from mia.state import QuoteSession, Stage
from mia.tools import Services


@pytest.fixture
def services(client, resolver):
    return Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)


@pytest.fixture
def state():
    return QuoteSession()


async def _route(state, services, said=None):
    return await tools.save_origin_destination(
        state,
        services,
        origin_city="Boston",
        origin_state="MA",
        destination_city="San Francisco",
        destination_state="CA",
        said=said,
    )


# --- route -------------------------------------------------------------------------------


async def test_saves_route(state, services):
    r = await _route(state, services)
    assert r["ok"]
    assert state.origin.zip == "02110"
    assert state.destination.spoken == "San Francisco, California"
    assert state.stage == Stage.ROUTE
    assert r["on_file"]["missing"] == ["vehicle"]
    assert "year, make and model" in r["next"]


async def test_saves_one_side_and_asks_for_the_other(state, services):
    r = await tools.save_origin_destination(state, services, origin_city="Boston")
    assert r["ok"]
    assert state.destination is None
    assert "destination" in r["next"]


async def test_unknown_city_keeps_the_other_side(state, services):
    r = await tools.save_origin_destination(
        state, services, origin_city="Boston", destination_city="Atlantis"
    )
    assert not r["ok"]
    assert r["error_code"] == "CITY_NOT_FOUND"
    assert r["failed"] == "destination"
    assert state.origin.city == "Boston"
    assert "Atlantis" in r["next"]


async def test_state_mismatch(state, services):
    r = await tools.save_origin_destination(
        state, services, origin_city="Boston", origin_state="FL"
    )
    assert r["error_code"] == "STATE_MISMATCH"
    assert "Boston" in r["next"] and "FL" in r["next"]


async def test_same_origin_and_destination(state, services):
    r = await tools.save_origin_destination(
        state, services, origin_city="Boston", destination_city="Bostin"
    )
    assert r["error_code"] == "SAME_ORIGIN_AND_DESTINATION"


async def test_geocoder_outage_escalates(state, services):
    r = await tools.save_origin_destination(state, services, origin_city="geofail")
    assert r["error_code"] == "GEOCODING_UNAVAILABLE"
    assert "request_human" in r["next"]


# --- grounding guardrail -------------------------------------------------------------------


async def test_refuses_cities_the_caller_never_said(state, services):
    r = await tools.save_origin_destination(
        state, services, origin_city="Los Angeles", origin_state="California", said="Yeah, sure"
    )
    assert r["error_code"] == "NOT_SAID_BY_CALLER"
    assert state.origin is None


async def test_drops_unsaid_state_but_keeps_city(state, services):
    r = await tools.save_origin_destination(
        state,
        services,
        origin_city="Boston",
        destination_city="San Francisco",
        destination_state="California",
        said="I need to send 2 cars from Boston to SF",
    )
    assert r["ok"]
    assert state.destination.zip == "94103"


async def test_saves_the_said_side_and_reports_the_invented_one(state, services):
    r = await tools.save_origin_destination(
        state,
        services,
        origin_city="Boston",
        destination_city="New York",
        said="from Boston",
    )
    assert r["ok"]
    assert state.destination is None
    assert r["ignored_not_said"] == ["destination New York"]


async def test_refuses_an_invented_vehicle(state, services):
    r = await tools.save_vehicle(
        state, services, year=2020, make="Toyota", model="Camry", said="Yeah sure. Boston to SF"
    )
    assert r["error_code"] == "NOT_SAID_BY_CALLER"
    assert state.vehicles == []


async def test_drops_an_invented_year(state, services):
    r = await tools.save_vehicle(
        state, services, year=2020, make="Toyota", model="4Runner", said="It's a Toyota 4Runner"
    )
    assert r["error_code"] == "MISSING_YEAR"
    assert "Toyota 4Runner" in r["next"]


# --- vehicles ------------------------------------------------------------------------------


async def test_saves_vehicle_with_quote_id(state, services):
    r = await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    assert r["ok"]
    assert r["saved"] == {"quote_id": "Q1", "vehicle": "2025 Honda Civic"}
    assert state.vehicles[0].trim_id == 34547
    assert state.stage == Stage.VEHICLES


async def test_typo_correction_is_reported(state, services):
    r = await tools.save_vehicle(state, services, year=2019, make="Toyota", model="Corola")
    assert r["saved"]["heard_as"] == {"Corola": "Corolla"}


async def test_expected_vehicle_count_drives_next_question(state, services):
    await _route(state, services)
    r = await tools.save_vehicle(
        state, services, year=2025, make="Honda", model="Civic", total_vehicles=2
    )
    assert r["on_file"]["missing"] == ["vehicle 2 of 2"]
    assert "vehicle 2" in r["next"] and "Don't confirm yet" in r["next"]
    r = await tools.save_vehicle(state, services, year=2020, make="Toyota", model="4Runner")
    assert r["on_file"]["missing"] == []
    assert "Read it back" in r["next"]


async def test_missing_model_asks_for_it_with_type_fallback(state, services):
    r = await tools.save_vehicle(state, services, year=2020, make="Toyota")
    assert r["error_code"] == "MISSING_MODEL"
    assert "model of the 2020 Toyota" in r["next"]
    assert "vehicle_type" in r["next"]


async def test_vehicle_type_fallback_is_an_estimate(state, services):
    r = await tools.save_vehicle(state, services, make="Toyota", vehicle_type="SUV")
    assert r["ok"]
    assert r["saved"] == {"quote_id": "Q1", "vehicle": "Toyota SUV", "estimate": True}
    assert "estimate" in r["next"]


async def test_ambiguous_model_lists_options(state, services):
    r = await tools.save_vehicle(state, services, year=2020, make="Chevrolet", model="Silverado")
    assert r["error_code"] == "AMBIGUOUS_MODEL"
    assert "Silverado 1500, Silverado 2500HD" in r["next"]


async def test_null_drivable_means_drivable(state, services):
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic", drivable=None)
    assert state.vehicles[0].operational is True


async def test_catalog_outage_escalates(state, services, fake_api):
    fake_api.fail_next(httpx.Response(402, json={}))
    r = await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    assert r["error_code"] == "PAYMENT_REQUIRED"
    assert "request_human" in r["next"]


# --- quote ---------------------------------------------------------------------------------


async def test_quote_needs_everything(state, services):
    r = await tools.get_quote(state, services)
    assert r["error_code"] == "MISSING_INFO"
    assert r["missing"] == ["origin", "destination", "vehicle"]


async def test_quote_reference_conversation_2(state, services):
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    await tools.save_vehicle(state, services, year=2020, make="Toyota", model="4Runner")
    r = await tools.get_quote(state, services)
    assert r["ok"]
    assert r["say"] == (
        "Your estimated cost is $2,311. It would be $1,291 for the Honda and $1,020 for the "
        "Toyota. You can discuss potential discounts for multiple vehicles with a licensed "
        "representative."
    )
    assert r["transit"] == "6 to 9 days door to door"
    assert state.stage == Stage.QUOTED
    assert state.quote["total"] == 2311


async def test_requoting_after_a_change_trashes_the_old_quote(state, services):
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    await tools.get_quote(state, services)
    await tools.save_vehicle(state, services, year=2020, make="Toyota", model="4Runner")
    assert state.quote is None
    assert state.trash[-1].kind == "quote"
    assert state.trash[-1].data["total"] == 1291


async def test_quote_service_error_escalates(state, services, fake_api):
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    fake_api.fail_next(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    r = await tools.get_quote(state, services)
    assert r["error_code"] == "UNAVAILABLE"
    assert "request_human" in r["next"]


async def test_filler_is_spoken_before_quoting(state, services):
    said = []
    services.before_quote = said.append
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    await tools.get_quote(state, services)
    assert said == ["Give me one second while I calculate your quote."]


async def test_the_price_waits_for_the_typing_sound(state, services):
    # The voice hook returns an awaitable (filler + ~2 s of typing); the result comes after it.
    order = []

    async def typing():
        await asyncio.sleep(0.05)
        order.append("typing done")

    services.before_quote = lambda _text: typing()
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    r = await tools.get_quote(state, services)
    order.append("quote returned")
    assert r["ok"] and order == ["typing done", "quote returned"]


async def test_a_stuck_sound_never_holds_the_price(state, services, monkeypatch):
    monkeypatch.setattr(tools, "MAX_QUOTE_PAUSE_SECONDS", 0.05)
    services.before_quote = lambda _text: asyncio.Event().wait()  # never finishes
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    assert (await tools.get_quote(state, services))["ok"]


# --- people --------------------------------------------------------------------------------


async def test_request_human_without_a_phone_line_is_only_noted(state, services):
    r = await tools.request_human(state, services, reason="asked for a human")
    assert state.human_requested and state.stage == Stage.TRANSFER
    assert r["transferring"] is False and state.transfer is None
    assert "licensed representative" in r["next"]


async def test_request_human_with_a_phone_line_starts_a_transfer(state, services):
    # The dial itself starts in agent.py once Mia's line is spoken, never inside the tool.
    started = []
    services.transfer = lambda: started.append(True)
    r = await tools.request_human(state, services, reason="asked for a human")
    assert r["transferring"] is True and state.transfer == "pending" and started == []
    assert "licensed representative" in r["next"]
    again = await tools.request_human(state, services)
    assert again["transferring"] is True and "already" in again["next"]


async def test_nothing_mia_says_names_sergio(state, services):
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    quoted = await tools.get_quote(state, services)
    assert "Sergio" not in quoted["next"] and "licensed representative" in quoted["next"]
    assert "Sergio" not in tools.ESCALATE


async def test_end_call_marks_ended_but_leaves_hang_up_to_the_agent(state, services):
    # The hang-up runs only after the goodbye is spoken (agent.py), never inside the tool.
    ended = []
    services.end_call = lambda: ended.append(True)
    r = await tools.end_call(state, services)
    assert state.ended and ended == []
    assert tools.CLOSING in r["next"]


async def test_quote_requires_the_callers_yes(state, services):
    await _route(state, services)
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic")
    r = await tools.get_quote(state, services, last_said="It's a 2019 Toyota Corolla")
    assert r["error_code"] == "NOT_CONFIRMED"
    assert state.quote is None
    r = await tools.get_quote(state, services, last_said="Yep")
    assert r["ok"]


@pytest.mark.parametrize(
    ("escalated", "asked", "kind"),
    [
        (False, False, "organic"),
        (False, True, "requested"),
        (True, False, "forced"),
        (True, True, "forced"),
    ],
)
async def test_transfer_kind(state, services, escalated, asked, kind):
    state.escalated = escalated
    await tools.request_human(state, services, asked=asked)
    assert state.transfer_kind == kind


async def test_a_failure_mia_cant_fix_makes_the_next_transfer_forced(state, services):
    r = tools._err(state, "API_DOWN", tools.ESCALATE)
    assert r["ok"] is False and state.escalated
    await tools.request_human(state, services, asked=False)
    assert state.transfer_kind == "forced"
    assert state.to_record()["transfer_kind"] == "forced"


async def test_save_vehicle_keeps_the_year_the_caller_corrected_to(state, services):
    said = "It's a twenty ten... twenty twenty Toyota 4Runner"
    r = await tools.save_vehicle(
        state, services, year=2010, make="Toyota", model="4Runner", said=said, last_said=said
    )
    assert r["ok"] and state.vehicles[0].year == 2020


async def test_a_vehicle_count_the_caller_never_said_is_ignored(state, services):
    said = "It's a twenty ten, twenty twenty Toyota 4Runner"
    await tools.save_vehicle(
        state,
        services,
        year=2010,
        make="Toyota",
        model="4Runner",
        total_vehicles=2,
        said=said,
        last_said=said,
    )
    assert state.expected_vehicles is None and state.vehicles[0].year == 2020
    said2 = "I have two cars, the first is a 2020 Toyota 4Runner"
    await tools.save_vehicle(
        state,
        services,
        year=2020,
        make="Toyota",
        model="4Runner",
        total_vehicles=2,
        said=said2,
        last_said=said2,
    )
    assert state.expected_vehicles == 2


# --- from Sergio's calls of 2026-11-11 ----------------------------------------------------------


async def test_city_nicknames_are_looked_up_by_their_name(state, services):
    said = "From NYC to Boston, Massachusetts"
    r = await tools.save_origin_destination(
        state,
        services,
        origin_city="NYC",
        destination_city="Boston",
        destination_state="Massachusetts",
        said=said,
    )
    assert r["ok"] and state.origin.city == "New York"


async def test_a_state_said_as_a_city_asks_which_city(state, services):
    # "I'm moving to Oregon": Mia said she couldn't find Oregon.
    said = "I'm moving to Oregon from Miami"
    r = await tools.save_origin_destination(
        state, services, origin_city="Miami", destination_city="Oregon", said=said
    )
    assert not r["ok"] and "which city in Oregon" in r["next"]
    assert state.origin and state.origin.city == "Miami"


async def test_a_model_that_is_the_make_is_no_model(state, services):
    # "it's my Jeep" -> save_vehicle(make="Jeep", model="Jeep") -> "couldn't find that model".
    r = await tools.save_vehicle(state, services, make="Honda", model="Honda", said="my Honda")
    assert r["error_code"] == "MISSING_MAKE_AND_MODEL" or r["error_code"].startswith("MISSING")
    assert "find" not in r["next"]


async def test_the_model_the_caller_said_is_filled_in(state, services):
    # "my twenty twenty Honda Civic" -> save_vehicle(2020, Honda): Mia asked for the model.
    said = "So I need to send my twenty twenty Honda Civic there from Miami."
    r = await tools.save_vehicle(state, services, year=2020, make="Honda", said=said)
    assert r["ok"] and state.vehicles[0].label == "2020 Honda Civic"


async def test_a_detail_dropped_again_and_again_offers_a_person(state, services):
    # 13 tries on 2026-11-11: the model was F-150, the caller's words didn't match.
    said = "It's a twenty twenty one Ford, the one I told you"
    codes = []
    for _ in range(3):
        r = await tools.save_vehicle(
            state, services, year=2021, make="Ford", model="Mustang", said=said
        )
        codes.append(r["next"])
    assert "representative" not in codes[0] and "representative" in codes[2]


async def test_a_state_without_a_city_asks_which_city(state, services):
    # Sergio, 2026-11-11: "if someone says the state and not the city, ask which city".
    said = "From Miami to California"
    r = await tools.save_origin_destination(
        state, services, origin_city="Miami", destination_state="California", said=said
    )
    assert r["ok"] and state.origin.city == "Miami"
    assert "Which city in California?" in r["next"]
    r = await tools.save_origin_destination(
        state, services, destination_state="California", said=said
    )
    assert "Which city in California?" in r["next"]
