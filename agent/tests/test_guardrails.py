from __future__ import annotations

import json

import pytest

from mia import guardrails
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


def test_end_call_always_runs():
    assert check_call("end_call", "{}", QuoteSession(), "", "") is None


OFFER = (
    "Your estimated cost is $724. Would you like me to connect you with a licensed representative?"
)


@pytest.mark.parametrize(
    ("last", "mia_last"),
    [
        ("Can I talk to a real person?", ""),
        ("I want to speak with an agent", "What's the year, make and model?"),
        ("Yeah, sure", OFFER),
        ("Yes please", OFFER),
    ],
)
def test_transfer_runs_when_the_caller_asks_or_accepts(last, mia_last):
    assert check_call("request_human", "{}", QuoteSession(), last, last, mia_last) is None


@pytest.mark.parametrize(
    ("last", "mia_last"),
    [
        ("", ""),  # invented: nobody asked (it would ring a real phone)
        ("Yeah, sure", "Shall we get started?"),  # a yes, but not to an offer
        ("No thanks", OFFER),
        ("No, I don't need an agent", OFFER),
        ("It's a 2020 Toyota", OFFER),
    ],
)
def test_transfer_is_dropped_otherwise(last, mia_last):
    reason = check_call("request_human", "{}", QuoteSession(), last, last, mia_last)
    assert reason == "caller did not ask for a person"


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


@pytest.mark.parametrize(
    "speech",
    [
        "Alright. If you have any other questions, just let me know. Otherwise, have a great day!",
        "Thank you for calling F&F. Have a great day!",
        "Goodbye!",
        "Okay, take care.",
    ],
)
def test_mias_goodbye_is_detected(speech):
    assert guardrails.is_goodbye(speech)


@pytest.mark.parametrize(
    "speech",
    [
        "Where are you shipping the car from, and where is it going?",
        "Your estimated cost is $724. Would you like me to connect you with Sergio?",
        # A greeting thanks them for calling but goes on with a question.
        "Thanks for calling F&F. I'm Mia. Shall we get started?",
    ],
)
def test_other_lines_are_not_goodbyes(speech):
    assert not guardrails.is_goodbye(speech)


@pytest.mark.parametrize(
    ("last", "allowed"),
    [
        ("What's the capital of France?", True),
        ("Tell me a joke about cats", True),
        ("What's your favorite pizza topping?", True),
        ("How much does it cost to ship a car?", False),  # about the quote
        ("Do you do enclosed transport?", False),
        ("Yeah, sure", False),
        ("I have two cars", False),
        ("", False),
    ],
)
def test_off_topic_only_counts_unrelated_questions(last, allowed):
    # The third one ends the call, so a turn about shipping must never count.
    reason = check_call("note_off_topic", "{}", QuoteSession(), last, last)
    assert (reason is None) == allowed


def test_after_an_answer_mia_asks_whats_missing():
    from mia.guardrails import keep_going

    s = QuoteSession(origin=BOS, destination=SF)
    assert keep_going("We only quote open car shipping.", s) == (
        "We only quote open car shipping. What's the year, make and model of the car?"
    )
    assert keep_going("Got it. What's the car?", s) == "Got it. What's the car?"  # has one


def test_keep_going_leaves_endings_and_complete_calls_alone():
    from mia.guardrails import keep_going

    s = QuoteSession(origin=BOS, destination=SF)
    assert keep_going("Thanks for calling F&F, goodbye!", s).endswith("goodbye!")
    s.transfer = "pending"
    assert keep_going("Connecting you now.", s) == "Connecting you now."
    done = QuoteSession(origin=BOS, destination=SF)
    done.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    done.quote = {"total": 1291}
    assert keep_going("The quote includes up to 100 pounds.", done).endswith("pounds.")


def test_keep_going_reads_back_when_all_is_on_file_but_not_quoted():
    from mia.guardrails import keep_going

    s = QuoteSession(origin=BOS, destination=SF)
    s.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    out = keep_going("We only quote open car shipping.", s)
    assert out == f"We only quote open car shipping. {read_back(s)}"
    s.escalated = True  # a failed lookup: Mia is offering a person, not the quote
    assert keep_going("A representative can help.", s) == "A representative can help."
