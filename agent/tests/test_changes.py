"""Stage 8: changing, removing and restoring vehicles (state.py, tools.py), and their
guardrails."""

from __future__ import annotations

import pytest
from fake_geo import fake_city_to_zip

from mia import grounding, tools
from mia.guardrails import check_call
from mia.state import QuoteSession
from mia.tools import Services

CIVIC = "It's a 2025 Honda Civic"
RUNNER = "and a 2020 Toyota 4Runner"


@pytest.fixture
def state():
    return QuoteSession()


@pytest.fixture
def services(client, resolver):
    return Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)


async def _quoted(state, services, *cars: str):
    said = "Boston, Massachusetts to San Francisco, California. " + " ".join(cars)
    await tools.save_origin_destination(
        state,
        services,
        origin_city="Boston",
        origin_state="MA",
        destination_city="San Francisco",
        destination_state="CA",
        said=said,
    )
    if CIVIC in cars:
        await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic", said=said)
    if RUNNER in cars:
        await tools.save_vehicle(
            state, services, year=2020, make="Toyota", model="4Runner", said=said
        )
    r = await tools.get_quote(state, services)
    assert r["ok"]
    return said


async def test_changing_the_vehicle_after_the_quote(state, services):
    said = await _quoted(state, services, CIVIC)
    old_id = state.vehicles[0].quote_id
    said += " Actually it's a 2020 Toyota 4Runner, not the Civic"
    r = await tools.update_vehicle(
        state, services, year=2020, make="Toyota", model="4Runner", said=said
    )
    assert r["ok"] and r["updated"]["to"] == "2020 Toyota 4Runner"
    assert state.vehicles[0].quote_id != old_id  # a new quote ID
    assert state.quote is None  # the old price is gone: read back and quote again
    assert any(t.kind == "vehicle" and t.reason == "vehicle updated" for t in state.trash)
    assert any(t.kind == "quote" for t in state.trash)
    assert "Read it back" in r["next"]


async def test_changing_only_the_year_keeps_make_and_model(state, services):
    said = await _quoted(state, services, CIVIC) + " sorry, it's a 2024"
    r = await tools.update_vehicle(state, services, year=2024, said=said)
    assert r["ok"] and state.vehicles[0].label == "2024 Honda Civic"


async def test_a_new_make_drops_the_old_model(state, services):
    said = await _quoted(state, services, CIVIC) + " it's actually a Toyota"
    r = await tools.update_vehicle(state, services, make="Toyota", said=said)
    assert not r["ok"]  # Toyota "Civic" doesn't exist: Mia asks for the model
    assert state.vehicles[0].label == "2025 Honda Civic"  # nothing changed


async def test_with_several_vehicles_mia_asks_which(state, services):
    said = await _quoted(state, services, CIVIC, RUNNER) + " make it a 2021"
    r = await tools.update_vehicle(state, services, year=2021, said=said)
    assert r["error_code"] == "WHICH_VEHICLE"
    runner = state.vehicles[1].quote_id
    r = await tools.update_vehicle(state, services, quote_id=runner, year=2021, said=said)
    assert r["ok"] and state.vehicles[1].label == "2021 Toyota 4Runner"
    assert state.vehicles[0].label == "2025 Honda Civic"


async def test_removing_a_vehicle(state, services):
    await _quoted(state, services, CIVIC, RUNNER)
    state.expected_vehicles = 2
    r = await tools.remove_vehicle(state, services, quote_id=state.vehicles[1].quote_id)
    assert r["ok"] and [v.label for v in state.vehicles] == ["2025 Honda Civic"]
    assert state.expected_vehicles == 1 and state.quote is None


async def test_the_only_vehicle_cant_be_removed(state, services):
    await _quoted(state, services, CIVIC)
    r = await tools.remove_vehicle(state, services)
    assert r["error_code"] == "ONLY_VEHICLE" and len(state.vehicles) == 1


async def test_undo_puts_the_vehicle_back_and_can_be_undone(state, services):
    said = await _quoted(state, services, CIVIC) + " Actually it's a 2020 Toyota 4Runner"
    original = state.vehicles[0].quote_id
    await tools.update_vehicle(
        state, services, year=2020, make="Toyota", model="4Runner", said=said
    )
    r = await tools.undo_last_change(state, services)
    assert r["ok"] and state.vehicles[0].label == "2025 Honda Civic"
    assert state.vehicles[0].quote_id == original  # restored, with its own quote ID
    await tools.undo_last_change(state, services)  # changed their mind again
    assert state.vehicles[0].label == "2020 Toyota 4Runner"


async def test_undo_a_removal(state, services):
    await _quoted(state, services, CIVIC, RUNNER)
    await tools.remove_vehicle(state, services, quote_id=state.vehicles[0].quote_id)
    await tools.undo_last_change(state, services)
    assert [v.label for v in state.vehicles] == ["2025 Honda Civic", "2020 Toyota 4Runner"]


async def test_undo_a_route_change(state, services):
    said = await _quoted(state, services, CIVIC) + " actually it's going to New York"
    await tools.save_origin_destination(
        state, services, destination_city="New York", destination_state="NY", said=said
    )
    assert state.destination.city == "New York"
    await tools.undo_last_change(state, services)
    assert state.destination.city == "San Francisco"


async def test_nothing_to_undo(state, services):
    r = await tools.undo_last_change(state, services)
    assert r["error_code"] == "NOTHING_TO_UNDO"


@pytest.mark.parametrize(
    ("name", "last", "allowed"),
    [
        ("remove_vehicle", "Remove the Toyota, please", True),
        ("remove_vehicle", "Actually just the Honda", True),
        ("remove_vehicle", "I don't need the second car", True),
        ("remove_vehicle", "Yes, that's correct", False),  # invented: would change the quote
        ("undo_last_change", "Actually, keep the Civic", True),
        ("undo_last_change", "Never mind, go back to the original", True),
        ("undo_last_change", "Sure", False),
    ],
)
def test_remove_and_undo_need_the_callers_words(name, last, allowed):
    reason = check_call(name, "{}", QuoteSession(), last, last)
    assert (reason is None) == allowed


def test_update_needs_a_detail_the_caller_said():
    said = "It's a 2025 Honda Civic. Actually make it a 2024"
    assert check_call("update_vehicle", '{"year": 2024}', QuoteSession(), said, said) is None
    assert check_call("update_vehicle", '{"year": 2019}', QuoteSession(), said, said) == (
        "no vehicle detail the caller said"
    )


def test_cues():
    assert grounding.wants_removal("forget the Toyota") and not grounding.wants_removal("yes")
    assert grounding.wants_undo("change it back") and not grounding.wants_undo("correct")


async def test_undo_and_save_of_the_same_car_keeps_one(state, services):
    # gpt-oss ran undo_last_change and save_vehicle(Civic) in one step after "never mind, keep
    # the Civic" (scenario undo_vehicle_change, 2026-11-10): the Civic was on file twice.
    said = await _quoted(state, services, CIVIC) + " Actually it's a 2020 Toyota 4Runner"
    await tools.update_vehicle(
        state, services, year=2020, make="Toyota", model="4Runner", said=said
    )
    await tools.undo_last_change(state, services)
    r = await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic", said=said)
    assert r["ok"] and r["saved"] is None
    assert [v.label for v in state.vehicles] == ["2025 Honda Civic"]


async def test_two_of_the_same_car_when_the_caller_said_two(state, services):
    said = "Boston, Massachusetts to San Francisco, California. Two cars, both 2025 Honda Civics"
    await tools.save_vehicle(
        state, services, year=2025, make="Honda", model="Civic", total_vehicles=2, said=said
    )
    await tools.save_vehicle(state, services, year=2025, make="Honda", model="Civic", said=said)
    assert [v.label for v in state.vehicles] == ["2025 Honda Civic", "2025 Honda Civic"]


async def test_two_makes_in_one_sentence_expect_two_cars(state, services):
    # Stage 7 simulation: "2022 Toyota RAV4 and 2017 Honda Civic", only the RAV4 was saved.
    said = "Boston to San Francisco. 2025 Honda Civic and 2020 Toyota 4Runner"
    await tools.save_vehicle(
        state, services, year=2025, make="Honda", model="Civic", said=said, last_said=said
    )
    assert state.expected_vehicles == 2
    assert "vehicle 2 of 2" in state.missing


async def test_the_model_alone_completes_the_vehicle_in_progress(state, services):
    # "a twenty twenty five Honda" one turn, "Civic" the next: the model passes only the model.
    said = "Boston, Massachusetts to San Francisco, California. A 2025 Honda. Civic"
    state.note_partial_vehicle({"year": 2025, "make": "Honda"})
    r = await tools.save_vehicle(state, services, model="Civic", said=said, last_said="Civic")
    assert r["ok"], r
    assert [v.label for v in state.vehicles] == ["2025 Honda Civic"]
    assert state.partial_vehicle == {}


def test_next_question_asks_only_for_whats_missing(state):
    from mia.state import Place

    state.origin = Place("Miami", "FL", "Florida", "33130")
    state.destination = Place("Chicago", "IL", "Illinois", "60601")
    state.note_partial_vehicle({"year": 2020, "make": "Honda"})
    nxt = tools._next_question(state)
    assert "2020 Honda" in nxt and "What model is the 2020 Honda?" in nxt


async def test_a_body_type_is_an_estimate_only_once_they_dont_know(state, services):
    # CONVERSATION_DESIGN: make only -> year and model; "I don't know" -> sedan, SUV or pickup.
    said = "Boston to San Francisco. It's a 2022 Toyota, an SUV"
    r = await tools.save_vehicle(
        state, services, year=2022, make="Toyota", vehicle_type="suv", said=said, unsure=False
    )
    assert not r["ok"] and "model" in r["next"] and "sedan" not in r["next"]
    assert state.vehicles == []
    r = await tools.save_vehicle(
        state, services, year=2022, make="Toyota", vehicle_type="suv", said=said, unsure=True
    )
    assert r["ok"] and r["saved"]["estimate"]


async def test_my_car_is_not_a_sedan(state, services):
    # Stage 7 simulation: "I'm looking to ship my car" grounded vehicle_type="sedan".
    said = "I'm looking to ship my car, it's a 2025 Honda"
    r = await tools.save_vehicle(
        state, services, year=2025, make="Honda", vehicle_type="sedan", said=said, unsure=True
    )
    assert not r["ok"] and state.vehicles == []


async def test_the_remembered_make_fills_in_even_with_a_body_type(state, services):
    said = "Boston to San Francisco. It's a Toyota. It's a 2022, but I don't know the model"
    state.note_partial_vehicle({"make": "Toyota", "year": 2022})
    r = await tools.save_vehicle(
        state, services, year=2022, vehicle_type="sedan", said=said, unsure=True
    )
    # "sedan" was never said: dropped; the Toyota is kept; they don't know the model -> types
    assert not r["ok"] and "sedan, SUV or pickup" in r["next"]
