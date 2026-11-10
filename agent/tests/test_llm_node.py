"""Mia.llm_node with a scripted model (offline): what's spoken when the guardrail drops the
model's whole step."""

from __future__ import annotations

from fake_geo import fake_city_to_zip
from livekit.agents.llm import ChatMessage
from scripted_llm import ScriptedLLM, Step

from mia.agent import Mia, new_session
from mia.prompt import GREETINGS
from mia.state import Place, QuoteSession
from mia.tools import Services

BOS = Place("Boston", "MA", "Massachusetts", "02110")
SF = Place("San Francisco", "CA", "California", "94103")
ENCLOSED = "We only quote open car shipping."


async def _reply(steps, state, said, client, resolver):
    model = ScriptedLLM(steps)
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        result = await session.run(user_input=said)
    spoken = [
        e.item.text_content
        for e in result.events
        if isinstance(e.item, ChatMessage) and e.item.role == "assistant"
    ]
    return " ".join(spoken), model.calls


async def test_a_question_gets_an_answer_when_the_step_is_dropped(client, resolver):
    # Live check, 2026-11-10: "do you do a closed shipping?" -> the model's only call was
    # dropped and Mia just repeated the vehicle question.
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [Step(calls=[("save_vehicle", '{"make": ""}')]), Step(text=ENCLOSED)]
    spoken, calls = await _reply(steps, state, "do you do a closed shipping?", client, resolver)
    assert spoken == f"{ENCLOSED} What's the year, make and model of the car?"
    assert calls[1]["tools"] == 0  # the retry offers no tools
    assert state.dropped_calls[0]["tool"] == "save_vehicle"


async def test_a_question_without_a_question_mark_counts(client, resolver):
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [Step(calls=[("save_vehicle", "{}")]), Step(text="It usually takes about a week.")]
    spoken, _ = await _reply(steps, state, "how long does it take", client, resolver)
    assert spoken.startswith("It usually takes about a week.")


async def test_no_question_keeps_the_fallback_line(client, resolver):
    # "Yeah, sure" + an invented city: the deterministic fallback, no extra model step.
    state = QuoteSession()
    steps = [Step(calls=[("save_origin_destination", '{"origin_city": ""}')])]
    spoken, calls = await _reply(steps, state, "Yeah, sure", client, resolver)
    assert spoken == "Where are you shipping the car from, and where is it going?"
    assert len(calls) == 1


async def test_an_empty_retry_falls_back(client, resolver):
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [Step(calls=[("save_vehicle", "{}")]), Step(text="")]
    spoken, _ = await _reply(steps, state, "can you do enclosed?", client, resolver)
    assert spoken == "What's the year, make and model of the car?"


async def test_an_answer_during_the_read_back_asks_to_confirm_again(client, resolver):
    # Live call, 2026-11-10: "Do you do enclosed shipping?" right after the read-back; Mia
    # answered and stopped, and silence ended the call before the quote.
    state = QuoteSession(origin=BOS, destination=SF)
    state.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1, trim_name="LX")
    spoken, _ = await _reply(
        [Step(text=ENCLOSED)], state, "Do you do enclosed shipping?", client, resolver
    )
    assert spoken.startswith(f"{ENCLOSED} Just to confirm, your 2025 Honda Civic")
    assert spoken.endswith("Is that correct?")
