from __future__ import annotations

import json

from mia.guardrails import check_call, fallback_line, read_back
from mia.state import Place, QuoteSession

BOS = Place("Boston", "MA", "Massachusetts", "02110")
SF = Place("San Francisco", "CA", "California", "94103")


def _args(**kw) -> str:
    return json.dumps(kw)


def test_drops_invented_city():
    s = QuoteSession()
    why = check_call(
        "save_origin_destination", _args(origin_city="Los Angeles"), s, "Yeah, sure", "Yeah, sure"
    )
    assert why == "no city the caller said"


def test_keeps_said_city():
    s = QuoteSession()
    said = "I need to send 2 cars from Boston to SF"
    args = _args(origin_city="Boston", destination_city="San Francisco")
    assert check_call("save_origin_destination", args, s, said, said) is None


def test_drops_invented_vehicle_but_keeps_real_one():
    s = QuoteSession()
    said = "My car is in Boston, Massachusetts and I'll send it to San Francisco, California"
    camry = _args(year=2020, make="Toyota", model="Camry")
    assert check_call("save_vehicle", camry, s, said, said)
    last = "It's a 2025 Honda Civic"
    civic = _args(year=2025, make="Honda", model="Civic")
    assert check_call("save_vehicle", civic, s, said + "\n" + last, last) is None


def test_drops_duplicate_save_in_same_turn():
    s = QuoteSession(caller_turns=3)
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    last = "It's a 2025 Honda Civic"
    civic = _args(year=2025, make="Honda", model="Civic")
    assert (
        check_call("save_vehicle", civic, s, last, last) == "same vehicle already saved this turn"
    )
    # On a later turn the same car is fine (e.g. a second identical car).
    s.caller_turns = 4
    assert check_call("save_vehicle", civic, s, last, "another 2025 Honda Civic") is None


def test_allows_repeat_when_caller_said_several():
    s = QuoteSession(caller_turns=2)
    s.add_vehicle(year=2020, make="Toyota", model="Corolla", trim_id=1)
    last = "two 2020 Toyota Corollas"
    corolla = _args(year=2020, make="Toyota", model="Corolla")
    assert check_call("save_vehicle", corolla, s, last, last) is None


def test_quote_needs_details_and_a_yes():
    s = QuoteSession(origin=BOS, destination=SF)
    assert check_call("get_quote", "{}", s, "", "Yep") is None  # the tool reports MISSING_INFO
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    assert check_call("get_quote", "{}", s, "", "It's a 2025 Honda Civic") == (
        "caller has not confirmed"
    )
    assert check_call("get_quote", "{}", s, "", "Yep") is None


def test_other_tools_always_run():
    s = QuoteSession()
    assert check_call("request_human", "{}", s, "", "") is None
    assert check_call("end_call", "{}", s, "", "") is None


def test_fallback_lines_follow_the_state():
    s = QuoteSession()
    assert fallback_line(s) == "Where are you shipping the car from, and where is it going?"
    s.origin = BOS
    assert fallback_line(s) == "And where is it going?"
    s.destination = SF
    s.expected_vehicles = 3
    assert fallback_line(s) == "What's the year, make and model of the first car?"
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    assert fallback_line(s) == "What's the year, make and model of the second car?"


def test_fallback_reads_back_when_complete():
    s = QuoteSession(origin=BOS, destination=SF)
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    assert fallback_line(s).startswith("Just to confirm")


def test_read_back():
    s = QuoteSession(origin=BOS, destination=SF)
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    s.add_vehicle(year=2020, make="Toyota", model="4Runner", trim_id=2)
    assert read_back(s) == (
        "Just to confirm, your 2025 Honda Civic and 2020 Toyota 4Runner will ship from Boston, "
        "Massachusetts to San Francisco, California. Is that correct?"
    )


def test_tidy_speech_drops_repeats_and_extra_questions():
    from mia.guardrails import tidy_speech

    q2 = "What's the year, make and model of the second car?"
    assert tidy_speech(q2 + q2) == q2
    assert tidy_speech("Thanks. " + q2 + "What's the year, make and model of the third car?") == (
        "Thanks. " + q2
    )
    quote = (
        "Your estimated cost is $2,311. It would be $1,291 for the Honda and $1,020 for the "
        "Toyota. Would you like me to connect you with Sergio?"
    )
    assert tidy_speech(quote) == quote
    assert tidy_speech("It ships in 4.5 days. Okay?") == "It ships in 4.5 days. Okay?"
    assert tidy_speech("") == ""
