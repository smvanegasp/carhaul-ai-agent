from __future__ import annotations

import pytest

from mia import grounding
from mia.grounding import (
    city_said,
    make_said,
    model_said,
    spoken_years,
    state_said,
    vehicle_type_said,
    year_said,
)


@pytest.mark.parametrize(
    "city, said",
    [
        ("Boston", "My car is in Boston, Massachusetts"),
        ("Boston", "from bostin to sf"),  # STT typo, model corrected it
        ("San Francisco", "I need to send 2 cars from Boston to SF"),
        ("San Francisco", "to san fran"),
        ("Los Angeles", "it's going to LA"),
        ("New York", "shipping it to NYC"),
        ("Las Vegas", "pick up in vegas"),
        ("Salt Lake City", "salt lake city utah"),
    ],
)
def test_city_said(city, said):
    assert city_said(city, said)


@pytest.mark.parametrize(
    "city, said",
    [
        ("Los Angeles", "Yeah, sure"),
        ("Boston", "I'm shipping from Austin"),
        ("San Francisco", "from Boston to San Diego"),
    ],
)
def test_city_not_said(city, said):
    assert not city_said(city, said)


@pytest.mark.parametrize(
    "state, said, ok",
    [
        ("Massachusetts", "Boston, MA", True),
        ("MA", "Boston Massachusetts", True),
        ("California", "to San Francisco, Califronia", True),  # typo
        ("New York", "to new york new york", True),
        ("California", "from Boston to SF", False),
    ],
)
def test_state_said(state, said, ok):
    assert state_said(state, said) is ok


@pytest.mark.parametrize(
    "make, said, ok",
    [
        ("Honda", "It's a 2025 Honda Civic", True),
        ("Chevrolet", "my chevy malibu", True),
        ("Mercedes-Benz", "a mercedes c class", True),
        ("Toyota", "It's a Toyota 4Runner from 2020", True),
        ("Toyota", "Yeah, sure", False),
        ("Honda", "a Toyota and a Ford", False),
    ],
)
def test_make_said(make, said, ok):
    assert make_said(make, said) is ok


@pytest.mark.parametrize(
    "model, said, ok",
    [
        ("4Runner", "a toyota four runner", True),
        ("4Runner", "a 4-Runner", True),
        ("CR-V", "honda crv", True),
        ("Civic", "honda civic", True),
        ("Camry", "Yeah, sure", False),
        ("Camry", "My car is in Boston, Massachusetts", False),  # "car" is not "Camry"
        ("Camry", "a toyota camri", True),
        ("Corolla", "a 2019 corola", True),
        ("A4", "an audi a5", False),
    ],
)
def test_model_said(model, said, ok):
    assert model_said(model, said) is ok


def test_spoken_years():
    assert "twenty twenty" in spoken_years(2020)
    assert "two thousand five" in spoken_years(2005)
    assert "twenty oh five" in spoken_years(2005)
    assert "nineteen ninety eight" in spoken_years(1998)
    assert "ninety eight" in spoken_years(1998)


@pytest.mark.parametrize(
    "year, said, ok",
    [
        (2020, "It's a Toyota 4Runner from 2020", True),
        (2020, "a twenty twenty toyota", True),
        (2019, "two thousand nineteen corolla", True),
        (2018, "an '18 civic", True),
        (1998, "a ninety eight civic", True),
        (2020, "Yeah, sure", False),
        (2021, "It's a 2020 Honda", False),
    ],
)
def test_year_said(year, said, ok):
    assert year_said(year, said) is ok


@pytest.mark.parametrize(
    "kind, said, ok",
    [
        ("suv", "it's some kind of SUV", True),
        ("pickup", "a pick up truck", True),
        ("sedan", "just a regular car", True),
        ("suv", "I don't know", False),
    ],
)
def test_vehicle_type_said(kind, said, ok):
    assert vehicle_type_said(kind, said) is ok


@pytest.mark.parametrize(
    "said, count",
    [
        ("I need to send 2 cars from Boston to SF", 2),
        ("I need to send three cars from Boston, MA to SF California", 3),
        ("both of my cars", 2),
        ("two of our vehicles", 2),
        ("I have 2 cars. Actually three cars.", 3),
        ("it's a 2020 Honda", None),
        ("my car is in Boston", None),
    ],
)
def test_vehicle_count_said(said, count):
    from mia.grounding import vehicle_count_said

    assert vehicle_count_said(said) == count


@pytest.mark.parametrize(
    "text, ok",
    [
        ("Yep", True),
        ("Correct", True),
        ("Yeah", True),
        ("aha", True),
        ("That's right", True),
        ("Sure, go ahead", True),
        ("No, it's a 2021", False),
        ("Yes but actually it's a 2021", False),
        ("It's a 2019 Toyota Corolla", False),
        ("Can you give me the price?", False),
    ],
)
def test_is_confirmation(text, ok):
    from mia.grounding import is_confirmation

    assert is_confirmation(text) is ok


@pytest.mark.parametrize(
    "text",
    [
        "Can I talk to a human?",
        "agent please",
        "I'd like to speak to a representative",
        "Can you connect me with someone?",
        "Yes, put me through to a real person",
    ],
)
def test_wants_person(text):
    assert grounding.wants_person(text)


@pytest.mark.parametrize(
    "text", ["No thanks", "I don't need an agent", "It's a 2020 Toyota", "Boston to Miami"]
)
def test_does_not_want_person(text):
    assert not grounding.wants_person(text)


def test_offered_person():
    assert grounding.offered_person(
        "Would you like me to connect you with a licensed representative?"
    )
    assert not grounding.offered_person("What's the year, make and model?")


@pytest.mark.parametrize(
    ("year", "said", "settled"),
    [
        # Sergio's call (2026-11-09): saved as 2010.
        (2010, "It's a twenty ten... twenty twenty Toyota", 2020),
        (2010, "twenty ten, no sorry, twenty twenty Corolla", 2020),
        (2010, "twenty ten uh I mean two thousand twenty one", 2021),
        (1998, "nineteen ninety eight actually nineteen ninety nine", 1999),
        (2018, "2018 2020", 2020),
        # Not corrections: two cars, or one year.
        (2019, "a 2019 and a 2020", 2019),
        (2020, "a 2019 and a 2020", 2020),
        (2019, "2019 Honda Civic", 2019),
        (None, "twenty ten twenty twenty", None),
    ],
)
def test_corrected_year(year, said, settled):
    assert grounding.corrected_year(year, said) == settled


@pytest.mark.parametrize(
    "text, asked",
    [
        ("do you do a closed shipping?", True),
        ("Before that, do you do enclosed shipping?", True),
        ("how long does it take", True),
        ("OK. And what about insurance", True),
        ("It's a Civic?", True),
        ("Yeah, sure", False),
        ("It's a twenty twenty Honda.", False),
        ("From Boston to San Francisco", False),
        ("", False),
    ],
)
def test_is_question(text, asked):
    assert grounding.is_question(text) is asked


@pytest.mark.parametrize(
    "said, count",
    [
        ("I've got a couple of vehicles to move", 2),
        ("a couple cars", 2),
        ("two of my cars", 2),
        ("we need both cars shipped", 2),
        ("a couple of days", None),
    ],
)
def test_vehicle_count_includes_a_couple(said, count):
    assert grounding.vehicle_count_said(said) == count


@pytest.mark.parametrize(
    "text, asks",
    [
        ("could you connect me to a live representative?", True),
        ("I want to talk to a human", True),
        ("a real person please", True),
        ("Can I speak with someone?", True),
        ("Someone else will drop it off", False),
        ("can someone call me back", False),
        ("no, I don't need to talk to a person", False),
        ("It's a 2020 Honda", False),
    ],
)
def test_asks_for_person(text, asks):
    # Stricter than wants_person: code runs request_human on it, and that rings a real phone.
    assert grounding.asks_for_person(text) is asks


@pytest.mark.parametrize(
    "text, n",
    [
        ("2022 Toyota RAV4 and 2017 Honda Civic.", 2),
        ("a twenty twenty-two Toyota RAV4, and a Honda Civic.", 2),
        ("a Chevy and a Ford F-150", 2),
        ("a 2025 Honda Civic", 1),
        ("It's a Honda, not a Toyota", 1),  # a correction, one car
        ("sorry, I mean the Toyota, the Honda's sold", 1),
    ],
)
def test_makes_named(text, n):
    assert grounding.makes_named(text) == n


@pytest.mark.parametrize(
    "text, heard",
    [
        (
            "It's from Miami to Chicago. It's a twenty twenty Honda.",
            {"year": 2020, "make": "Honda"},
        ),
        ("a 2019... no 2020 Chevy", {"year": 2020, "make": "Chevrolet"}),
        ("It's a Toyota", {"make": "Toyota"}),
        ("From Boston to SF", {}),
        ("a Honda and a Toyota", {}),  # two cars: no single make
    ],
)
def test_vehicle_details_in(text, heard):
    assert grounding.vehicle_details_in(text) == heard


def test_unsure_and_offered_types():
    assert grounding.unsure("I'm not exactly sure of the model")
    assert grounding.unsure("I don't know")
    assert not grounding.unsure("It's a Civic")
    assert grounding.offered_types("Is it a sedan, an SUV, or a pickup?")
    assert not grounding.offered_types("What model is the 2020 Honda?")
    assert not grounding.vehicle_type_said("sedan", "I'm looking to ship my car")
    assert grounding.vehicle_type_said("sedan", "just a regular car")
    assert grounding.vehicle_type_said("suv", "it's an SUV")


@pytest.mark.parametrize(
    "text, n",
    [
        ("a twenty ten... no sorry, twenty twenty-two Toyota RAV4 and a 2017 Honda Civic.", 2),
        ("one's a Honda and the other's a Toyota", 2),
        ("a Honda, no wait, a Toyota", 1),
        ("2025 Honda Civic and 2020 Toyota 4Runner", 2),
    ],
)
def test_makes_named_corrections_only_between_makes(text, n):
    assert grounding.makes_named(text) == n


def test_two_cars_are_not_a_partial_vehicle():
    assert grounding.vehicle_details_in("2025 Honda Civic and 2020 Toyota 4Runner") == {}
    assert grounding.vehicle_count_said("I've got a couple of rides to move") == 2


def test_actually_before_a_count_is_not_a_correction():
    said = (
        "I've actually got two vehicles, first, a 2025 Honda Civic that's running fine, and "
        "second, a 2020 Toyota 4Runner"
    )
    assert grounding.makes_named(said) == 2
    assert grounding.vehicle_details_in(said) == {}
    assert grounding.vehicle_details_in("a 2025 Civic and a 2020 4Runner") == {}
    assert grounding.vehicle_details_in("a twenty ten, no sorry, twenty twenty Honda") == {
        "year": 2020,
        "make": "Honda",
    }


@pytest.mark.parametrize(
    "model, make, said, named",
    [
        ("Civic", "Honda", "send my twenty twenty Honda Civic there from Miami", True),
        ("Civic", "Honda", "a Honda, the Civic", True),
        ("Model 3", "Tesla", "a 2021 Tesla Model 3", True),
        ("Fit", "Honda", "a Honda, it doesn't fit in the garage", False),
        ("Civic", "Honda", "my neighbor has a Civic, mine is a Honda", False),
    ],
)
def test_model_named_right_after_the_make(model, make, said, named):
    assert grounding.model_named(model, make, said) is named


def test_punctuation_is_never_a_detail_the_caller_said():
    # Real-API run, 2026-11-11: "Yeah, sure" -> save_origin_destination(origin_city="?").
    assert not grounding.city_said("?", "Yeah, sure")
    assert not grounding.model_said("?", "it's my Ford")


def test_a_make_or_a_year_is_on_topic():
    # "It's a 2025 Honda Civic" was counted as an off-topic question.
    assert grounding.is_on_topic("It's a 2025 Honda Civic")
    assert grounding.is_on_topic("It's a Toyota 4Runner from 2020")
    assert not grounding.is_on_topic("Tell me a joke about cats")


# --- Belinda's calls, 2026-11-11 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        (
            "I want to know if you offer enclosed like, shippings, and I'm sending my car from "
            "Miami to Chicago.",
            True,
        ),
        ("I'm moving to Chicago. Do you do enclosed", True),
        ("I was wondering how long it takes", True),
        ("Yeah, sure", False),
        ("It's a twenty twenty Honda.", False),
        ("Yeah. That's correct.", False),
    ],
)
def test_is_question_anywhere_in_the_message(text, ok):
    assert grounding.is_question(text) is ok


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("Cool. Thank you. Bye.", True),
        ("What? Goodbye.", True),
        ("Okay, bye bye", True),
        ("Thank you", False),
        ("I said goodbye to my old car, now it's a 2020 Honda Civic from Miami", False),
    ],
)
def test_is_farewell(text, ok):
    assert grounding.is_farewell(text) is ok


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("No, thank you.", True),
        ("Nope, I'm good.", True),
        ("No thanks, that's all", True),
        ("Not right now, thanks", True),
        ("Thank you", False),
        ("Okay", False),
        ("Yes please", False),
        ("No, but how long does it take?", False),
        ("No, I want to change the car", False),
    ],
)
def test_declines(text, ok):
    assert grounding.declines(text) is ok


def test_vehicle_mentions_split_each_car():
    said = (
        "We're moving from Atlanta to Portland. With a twenty twenty two Toyota RAV four and a "
        "two thousand seventeen Honda Civic."
    )
    found = grounding.vehicle_mentions(said)
    assert [(m["year"], m["make"]) for m in found] == [(2022, "Toyota"), (2017, "Honda")]
    assert found[1]["words"] == "honda civic"
    merc = grounding.vehicle_mentions("a 2019 Mercedes-Benz C300 and a 2020 Ford F-150")
    assert [(m["year"], m["make"]) for m in merc] == [(2019, "Mercedes-Benz"), (2020, "Ford")]


@pytest.mark.parametrize(
    ("said", "ok"),
    [
        ("Corolla.", True),
        ("It's a Corolla", True),
        ("Yeah, the Corolla", True),
        ("corolla is not right it is a camry", False),
        ("Hi there", False),
    ],
)
def test_model_alone(said, ok):
    assert grounding.model_alone("Corolla", said) is ok


@pytest.mark.parametrize(
    ("said", "route"),
    [
        (
            "I want to know if you offer enclosed like, shippings, and I'm sending my car from "
            "Boston, Massachusetts to San Francisco, California.",
            ("Boston", "Massachusetts", "San Francisco", "California"),
        ),
        (
            "I need to send my twenty twenty Honda from Miami to Chicago. Now",
            ("Miami", None, "Chicago", None),
        ),
        (
            "I'm moving from Boston to San Francisco next week, do you do enclosed?",
            ("Boston", None, "San Francisco", None),
        ),
        ("From Miami to California.", None),  # a state: Mia asks which city
        ("It goes from bad to worse", None),
        ("Yeah, sure", None),
    ],
)
def test_route_in(said, route):
    found = grounding.route_in(said)
    if route is None:
        assert found is None
    else:
        assert found is not None
        assert (
            found["origin_city"],
            found["origin_state"],
            found["destination_city"],
            found["destination_state"],
        ) == route
