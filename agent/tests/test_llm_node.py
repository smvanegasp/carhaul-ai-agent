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


async def test_a_garbled_removal_is_asked_back_then_done(client, resolver):
    # Sergio's call: STT heard "eliminate" as "tell him Nate"; the removal was dropped and Mia
    # read the same three cars back three times. Now she asks, and a yes removes it.
    state = QuoteSession(origin=BOS, destination=SF)
    state.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=1)
    state.add_vehicle(year=2020, make="Toyota", model="4Runner", trim_id=2)
    toyota = state.vehicles[1].quote_id
    remove = ("remove_vehicle", f'{{"quote_id": "{toyota}"}}')
    model = ScriptedLLM(
        [
            Step(calls=[remove]),  # "tell him Nate": dropped, the question is asked
            Step(calls=[remove]),  # "Yes": runs
            Step(text="I've removed the 2020 Toyota 4Runner. Is that correct?"),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        first = await session.run(user_input="No. I won't tell him Nate to tell you about that.")
        asked = [e.item.text_content for e in first.events if isinstance(e.item, ChatMessage)]
        assert asked[-1] == "Do you want me to remove the 2020 Toyota 4Runner?"
        await session.run(user_input="Yes")
    assert [v.label for v in state.vehicles] == ["2025 Honda Civic"]


async def test_a_detail_mia_proposed_and_the_caller_confirmed_counts(client, resolver):
    # Sergio's call: "Is it a Ford F-150?" "Yeah. That's correct." -> save_vehicle(F-150) was
    # refused four times because "F-150" wasn't in the caller's own words.
    state = QuoteSession(origin=BOS, destination=SF)
    f150 = ("save_vehicle", '{"year": 2021, "make": "Ford", "model": "F-150"}')
    model = ScriptedLLM(
        [
            Step(text="I'm sorry, I didn't catch the model. Is it a Ford F-150?"),
            Step(calls=[f150]),
            Step(text="Got it."),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="It's a twenty twenty one Ford, it suffered one hundred")
        await session.run(user_input="Yeah. That's correct.")
    assert [v.label for v in state.vehicles] == ["2021 Ford F-150"]


async def test_a_yes_to_the_read_back_gets_the_quote(client, resolver):
    # Sergio's call: "Yep" to the read-back, no get_quote, and Mia read it all back again.
    state = QuoteSession(origin=BOS, destination=SF)
    state.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=34547)
    read_back = (
        "Just to confirm, your 2025 Honda Civic will ship from Boston to SF. Is that correct?"
    )
    model = ScriptedLLM(
        [Step(text=read_back), Step(text=read_back), Step(text="Your estimated cost is $1,291.")]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="It's a 2025 Honda Civic")
        await session.run(user_input="Yep.")
    assert state.quote and state.quote["total"] == 1291


async def test_a_third_off_topic_question_in_a_row_ends_the_call(client, resolver):
    # The model often doesn't count the third one (off_topic_three_strikes turned CI red).
    state = QuoteSession()
    off = ("note_off_topic", "{}")
    model = ScriptedLLM(
        [
            Step(calls=[off]),
            Step(text="Not sure. Where are you shipping from?"),
            Step(calls=[off]),
            Step(text="Not sure. Where are you shipping from?"),
            Step(text="I'm not sure about that. Where are you shipping from?"),
            Step(text="I can only help with car shipping quotes. Thanks for calling. Goodbye!"),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="What's the capital of France?")
        await session.run(user_input="Tell me a joke about cats?")
        await session.run(user_input="What's your favorite pizza topping?")
    assert state.off_topic == 3 and state.ended and state.end_reason == "off_topic"


def test_the_greeting_asks_the_first_question():
    # Sergio, 2026-11-11: no "Shall we start?"; the greeting itself asks for the route.
    for greeting in GREETINGS:
        assert greeting.endswith("?") and "start" not in greeting.lower()
        assert "virtual assistant" in greeting


# --- Belinda's calls, 2026-11-11 ---------------------------------------------------------------


def _outputs(model, step):
    return [i.output for i in model.contexts[step].items if i.type == "function_call_output"]


async def test_two_cars_named_with_the_route_are_both_saved(client, resolver):
    # Call 2cd0a119e59d: route and two cars in one message; the model saved only the route and
    # asked for "the first vehicle" ("I already gave you that information").
    state = QuoteSession()
    route = '{"origin_city": "Boston", "destination_city": "San Francisco"}'
    model = ScriptedLLM(
        [Step(calls=[("save_origin_destination", route)]), Step(text="Is that correct?")]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    said = (
        "We're moving from Boston to San Francisco. With a twenty twenty two Toyota RAV four "
        "and a two thousand seventeen Honda Civic."
    )
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input=said)
    assert [v.label for v in state.vehicles] == ["2022 Toyota RAV4", "2017 Honda Civic"]
    assert not state.missing


async def test_the_model_said_alone_after_did_you_mean_is_saved(client, resolver):
    # Call 2f6b9240a6da: "Corolla." to "Did you mean a Corolla, Camry Solara, or GR Corolla?"
    # was never saved; the quote then failed and Mia asked for the model again.
    state = QuoteSession(origin=BOS, destination=SF)
    model = ScriptedLLM(
        [
            Step(text="I couldn't find that. Did you mean a Corolla, Camry Solara, or GR Corolla?"),
            Step(text="Got it, a 2020 Toyota Corolla. Is that everything?"),
            Step(text="Just to confirm."),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="It's a twenty twenty Toyota Acarola.")
        await session.run(user_input="Corolla.")
    assert [v.label for v in state.vehicles] == ["2020 Toyota Corolla"]


async def test_a_bare_word_is_not_a_model_unless_mia_asked_for_it(client, resolver):
    state = QuoteSession(origin=BOS, destination=SF)
    model = ScriptedLLM([Step(text="Where is it going?"), Step(text="Okay.")])
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="It's a twenty twenty Toyota")
        await session.run(user_input="Corolla.")
    assert state.vehicles == []


async def test_goodbye_ends_the_call(client, resolver):
    # Call 97f388f57b75: "Cool. Thank you. Bye." then "What? Goodbye." -> no end_call; Mia
    # read the details back twice.
    state = QuoteSession(origin=BOS, destination=SF)
    state.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=34547)
    state.quote = {"total": 1291}
    read_back = "Just to confirm, your 2025 Honda Civic will ship. Is that correct?"
    model = ScriptedLLM(
        [
            Step(calls=[("request_human", '{"reason": "x"}')]),
            Step(text=f'"{read_back}"'),
            Step(text="Thanks for calling F&F! Have a nice day!"),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="Cool. Thank you. Bye.")
    assert state.ended and state.end_reason == "mia"
    assert state.transfer is None  # the invented request_human never ran
    assert "Thanks for calling F&F!" in _outputs(model, 1)[-1]


async def test_no_to_the_representative_after_the_quote_ends_the_call(client, resolver):
    # Sergio: after "no" to the licensed representative, close the call; no "anything else?".
    state = QuoteSession(origin=BOS, destination=SF)
    state.add_vehicle(year=2025, make="Honda", model="Civic", trim_id=34547)
    state.quote = {"total": 1291}
    model = ScriptedLLM(
        [
            Step(
                text="Your estimated cost is $1,291. Would you like me to connect you with a "
                "licensed representative who can assist you further?"
            ),
            Step(text="No problem. Is there anything else I can help you with?"),
            Step(text="Thanks for calling F&F! Have a nice day!"),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="Okay")
        result = await session.run(user_input="No, thank you.")
    spoken = [e.item.text_content for e in result.events if isinstance(e.item, ChatMessage)]
    assert state.ended
    assert not any("anything else" in s for s in spoken)


async def test_no_before_the_quote_does_not_end_the_call(client, resolver):
    state = QuoteSession(origin=BOS, destination=SF)
    model = ScriptedLLM(
        [
            Step(text="Would you like me to connect you with a licensed representative?"),
            Step(text="Okay. What's the year, make and model?"),
        ]
    )
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    async with new_session(state, llm=model) as session:
        await session.start(Mia(services, greeting=GREETINGS[0]))
        await session.run(user_input="Hmm")
        await session.run(user_input="No, thank you.")
    assert not state.ended


async def test_a_question_with_the_route_is_answered_first(client, resolver):
    # Call 02784d4eb839: "I want to know if you offer enclosed like, shippings, and I'm sending
    # my car from Miami to Chicago" -> the route was saved and the question ignored.
    state = QuoteSession()
    route = '{"origin_city": "Boston", "destination_city": "San Francisco"}'
    model = ScriptedLLM(
        [
            Step(calls=[("save_origin_destination", route)]),
            Step(text="Got it, Boston to San Francisco. What year, make and model is it?"),
        ]
    )
    said = (
        "I want to know if you offer enclosed like, shippings, and I'm sending my car from "
        "Boston to San Francisco."
    )
    spoken, _ = await _reply_with(model, state, said, client, resolver)
    assert '"next": "The caller also asked a question' in _outputs(model, 1)[-1]
    assert ENCLOSED in _outputs(model, 1)[-1]
    # And code makes sure the fact is said, whatever the model does.
    assert spoken.startswith(ENCLOSED)
    assert spoken.endswith("What year, make and model is it?")


async def _reply_with(model, state, said, client, resolver):
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


async def test_an_early_try_on_a_partial_transcript_doesnt_block_the_final_one(client, resolver):
    # Call fc039e1f645f: LiveKit's preemptive generation tried "...my twenty twenty Toyota"
    # first and used up the turn's save_vehicle; "Toyota Corolla" in the final message was then
    # never saved and Mia asked "What model is the 2020 Toyota?".
    state = QuoteSession()
    state.caller_turns, state.last_said = 1, "I need to set up my twenty twenty Toyota"
    assert state.code_ran_once("save_vehicle")  # the early try, thrown away
    route = '{"origin_city": "Boston", "destination_city": "San Francisco"}'
    model = ScriptedLLM(
        [Step(calls=[("save_origin_destination", route)]), Step(text="Is that correct?")]
    )
    said = "I need to set up my twenty twenty Toyota Corolla from Boston to San Francisco, please."
    await _reply_with(model, state, said, client, resolver)
    assert [v.label for v in state.vehicles] == ["2020 Toyota Corolla"]


def test_code_runs_once_per_message():
    state = QuoteSession()
    state.caller_turns, state.last_said = 1, "a 2020 Toyota Corolla"
    assert state.code_ran_once("save_vehicle")
    assert not state.code_ran_once("save_vehicle")  # same message: no repeats
    state.caller_turns = 2
    assert state.code_ran_once("save_vehicle")  # a new message
