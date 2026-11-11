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
    # The FAQ still gets its answer from code (faq.py), then the next question.
    assert spoken == f"{ENCLOSED} What's the year, make and model of the car?"


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


async def test_a_failed_retry_falls_back_without_crashing_the_turn(client, resolver):
    # Stage 7 simulation: with no tools offered gpt-oss still called one and Groq rejected it
    # ("Tool choice is none, but model called a tool"); 4 retries later the turn crashed.
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [
        Step(calls=[("save_vehicle", "{}")]),
        Step(error="Tool choice is none, but model called a tool"),
    ]
    spoken, calls = await _reply(steps, state, "do you do enclosed?", client, resolver)
    # The FAQ still gets its answer from code (faq.py), then the next question.
    assert spoken == f"{ENCLOSED} What's the year, make and model of the car?"
    assert len(calls) == 2  # one attempt, no retries


async def test_a_plain_request_for_a_person_runs_request_human(client, resolver):
    # Stage 7 simulation: "could you connect me to a live representative?" -> the model called
    # note_off_topic (dropped) and Mia asked for the car again.
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [
        Step(calls=[("note_off_topic", '{"topic": "representative"}')]),
        Step(text="Sure, I'll connect you with a licensed representative now."),
    ]
    said = "Sure, but could you connect me to a live representative? I'd rather talk to a person."
    spoken, _ = await _reply(steps, state, said, client, resolver)
    assert state.human_requested
    assert "representative" in spoken


async def test_a_mention_of_someone_never_rings_the_phone(client, resolver):
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [Step(calls=[("save_vehicle", "{}")])]
    spoken, _ = await _reply(steps, state, "Someone else will drop it off", client, resolver)
    assert not state.human_requested
    assert spoken == "What's the year, make and model of the car?"


async def test_the_retry_sees_no_tool_calls_in_its_history(client, resolver):
    # With tool calls in its history gpt-oss kept calling tools even with none offered.
    state = QuoteSession(origin=BOS, destination=SF)
    model = ScriptedLLM([Step(calls=[("save_vehicle", "{}")]), Step(text=ENCLOSED)])
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="do you do enclosed?")
    retry = model.contexts[1]
    assert not [i for i in retry.items if i.type in ("function_call", "function_call_output")]
    assert "No tools" in retry.items[-1].text_content


async def test_a_failed_model_step_keeps_the_call_going(client, resolver):
    # Stage 7 simulation: "Failed to parse tool call arguments as JSON" ended 3 of 72 calls.
    state = QuoteSession(origin=BOS, destination=SF)
    steps = [Step(error="Failed to parse tool call arguments as JSON")]
    spoken, calls = await _reply(steps, state, "Okay, go ahead", client, resolver)
    assert spoken == "What's the year, make and model of the car?"
    assert len(calls) == 1  # not retryable: no second attempt


async def test_a_year_and_make_said_with_the_route_are_kept(client, resolver):
    # Sergio's call, 2026-11-10: "It's from Miami to Chicago. It's a twenty twenty Honda." ->
    # the route was saved, then Mia asked for the year, make and model again, because the
    # route tool told the model to.
    state = QuoteSession()
    route = '{"origin_city": "Boston", "destination_city": "San Francisco"}'
    model = ScriptedLLM(
        [Step(calls=[("save_origin_destination", route)]), Step(text="What model is it?")]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    said = "It's from Boston to San Francisco. It's a twenty twenty five Honda."
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input=said)
    assert state.partial_vehicle == {"year": 2025, "make": "Honda"}
    outputs = [i.output for i in model.contexts[1].items if i.type == "function_call_output"]
    assert "What model is the 2025 Honda?" in outputs[-1]
    assert '"heard_so_far": "2025 Honda"' in outputs[-1]
