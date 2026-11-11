"""The Mia agent: LiveKit function tools over mia.tools, plus the LLM factory."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncIterable, Awaitable
from typing import Any

from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentSession,
    APIConnectOptions,
    ChatContext,
    RunContext,
    SessionConnectOptions,
    function_tool,
    llm,
)
from livekit.plugins import groq

from mia import faq, grounding, guardrails, speech, tools
from mia.prompt import INSTRUCTIONS, pick_greeting
from mia.state import QuoteSession
from mia.tools import OFF_TOPIC_LIMIT, Services, model_from_words

DEFAULT_MODEL = "openai/gpt-oss-20b"


logger = logging.getLogger("mia")

# Tool rounds per caller turn before Mia must answer. Invented calls are dropped before they run
# (guardrails.py), so real turns need 1-2; the last round forces a plain answer, which
# gpt-oss sometimes breaks by calling a tool anyway, so keep headroom.
MAX_TOOL_STEPS = 3


class GroqLLM(groq.LLM):
    """groq.LLM with two fixes for gpt-oss tool calling (both seen on 2026-11-08):

    - The plugin sends OpenAI "strict" schemas, which make every parameter required; gpt-oss
      leaves optional ones out and Groq rejects the call ("did not match schema"). Like
      openai.LLM.with_cerebras/with_sambanova, we turn strict schemas off.
    - After ``max_tool_steps`` LiveKit asks for a plain answer with ``tool_choice="none"``;
      gpt-oss sometimes calls a tool anyway and Groq fails the request ("Tool choice is none,
      but model called a tool"). Sending no tools at all makes that impossible.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._strict_tool_schema = False

    def chat(self, *, tools=None, tool_choice=NOT_GIVEN, **kwargs: Any):
        if tool_choice == "none":
            tools, tool_choice = None, NOT_GIVEN
        return super().chat(tools=tools, tool_choice=tool_choice, **kwargs)


def make_llm(model: str | None = None) -> GroqLLM:
    """Groq LLM. MIA_LLM_MODEL overrides the model (e.g. openai/gpt-oss-120b to compare)."""
    model = model or os.environ.get("MIA_LLM_MODEL") or DEFAULT_MODEL
    return GroqLLM(
        model=model,
        temperature=0.3,
        # gpt-oss reasons before answering; "low" keeps the voice latency down. Other models
        # (Qwen) don't take this setting.
        reasoning_effort="low" if "gpt-oss" in (model or DEFAULT_MODEL) else NOT_GIVEN,
        # Route and vehicle in one step for callers who say both; invented extras are dropped.
        parallel_tool_calls=True,
    )


def new_session(state: QuoteSession, llm=None, **kwargs: Any) -> AgentSession[QuoteSession]:
    """The session settings every entry point shares (text chat, tests, voice worker)."""
    kwargs.setdefault("conn_options", CONN_OPTIONS)
    return AgentSession[QuoteSession](
        llm=llm or make_llm(), userdata=state, max_tool_steps=MAX_TOOL_STEPS, **kwargs
    )


# One quick LLM retry, not LiveKit's 3 at 2 s apart: a step that fails (gpt-oss's broken tool
# JSON, stage 7) is answered with the fallback line within about a second instead of 6+ s of
# silence. STT and TTS keep LiveKit's defaults.
CONN_OPTIONS = SessionConnectOptions(
    llm_conn_options=APIConnectOptions(max_retry=1, retry_interval=0.5, timeout=10.0)
)


ANSWER_ONLY = (
    "Answer the caller's last question in one or two short sentences, only from your "
    "instructions (offer a licensed representative if they don't cover it). No tools "
    "this time: just speak."
)


# Mia just asked for the model ("What model is the 2020 Toyota?", "Did you mean a Corolla,
# Camry Solara, or GR Corolla?"): a one-word answer is then the model.
_ASKED_MODEL = re.compile(r"\bmodel\b[^.!]*\?|\bdid you mean\b", re.IGNORECASE)

# A question in the same message as details (call 02784d4eb839, 2026-11-11: "I want to know if
# you offer enclosed like, shippings, and I'm sending my car from Miami to Chicago" -> the route
# was saved and the question ignored). The tool's `next` then starts with this.
ANSWER_FIRST = (
    "The caller also asked a question in this message: answer it first in one short sentence "
    "(only from your instructions; offer a licensed representative if they don't cover it), "
    "then: "
)
_ANSWER_FIRST_TOOLS = {"save_origin_destination", "save_vehicle", "update_vehicle"}


def _answer_first(name: str, result: dict[str, Any], last_said: str | None) -> dict[str, Any]:
    """Put the caller's question first in a tool's `next`, so it isn't lost behind the slot."""
    if (
        name not in _ANSWER_FIRST_TOOLS
        or not last_said
        or not isinstance(result.get("next"), str)
        or not grounding.is_question(last_said)
        or grounding.is_short_yes(last_said)
    ):
        return result
    known = faq.asked_about(last_said)
    hint = ANSWER_FIRST
    if known:
        hint = f'The caller also asked a question: answer it first ("{known.answer}"), then: '
    return {**result, "next": hint + result["next"]}


def _note_partial_vehicle(state: QuoteSession, last_said: str) -> None:
    """While a vehicle is missing, keep the year and make the caller just said, whatever tools
    the model calls (in Sergio's call it called none for "It's a twenty twenty Honda"). Not
    once a vehicle was saved from this same message, nor after the quote (changes then go
    through update_vehicle)."""
    if state.quote or not any(m.startswith("vehicle") for m in state.missing):
        return
    # Two makes in one message is two cars, whatever the model saves (stage 7 simulation:
    # "one's a Honda and the other's a Toyota" with only the route saved).
    named = grounding.makes_named(last_said)
    if named >= 2 and named > (state.expected_vehicles or 0):
        state.expected_vehicles = named
    if any(v.saved_turn == state.caller_turns for v in state.vehicles):
        return
    heard = grounding.vehicle_details_in(last_said)
    # "It's a 2022, but I don't know the model": remembered, so Mia stops asking for it
    # (scenario estimate_after_unsure: she asked "What model is the 2022 Toyota?" again).
    if grounding.unsure(last_said) and (heard or state.partial_vehicle):
        heard["model_unknown"] = True
    if heard:
        state.note_partial_vehicle(heard)


def _call_chunk(name: str, args: dict[str, Any]) -> llm.ChatChunk:
    """A tool call added by code (see ``Mia.llm_node``)."""
    call = llm.FunctionToolCall(
        name=name, arguments=json.dumps(args), call_id=f"mia_{uuid.uuid4().hex[:12]}"
    )
    return llm.ChatChunk(
        id=call.call_id, delta=llm.ChoiceDelta(role="assistant", tool_calls=[call])
    )


def caller_said(chat_ctx: ChatContext) -> str:
    """Everything the caller has said so far (for the grounding guardrail)."""
    return "\n".join(
        item.text_content or ""
        for item in chat_ctx.items
        if getattr(item, "type", None) == "message" and item.role == "user"
    )


def grounded_said(chat_ctx: ChatContext) -> str:
    """What the caller said, plus Mia's last line when they just said yes to it: "Is it a
    Ford F-150?" "Yeah, that's correct." means they said F-150 (Sergio's call, 2026-11-11:
    four yeses and the model still wasn't accepted)."""
    said, last = caller_said(chat_ctx), caller_last_said(chat_ctx)
    if grounding.is_confirmation(last):
        said = f"{said} {mia_last_said(chat_ctx)}"
    return said


def caller_turn_count(chat_ctx: ChatContext) -> int:
    return sum(
        1
        for item in chat_ctx.items
        if getattr(item, "type", None) == "message" and item.role == "user"
    )


def mia_last_said(chat_ctx: ChatContext) -> str:
    """Mia's latest line (did she just offer to connect them with someone?)."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and item.role == "assistant":
            return item.text_content or ""
    return ""


def caller_last_said(chat_ctx: ChatContext) -> str:
    """The caller's latest message."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and item.role == "user":
            return item.text_content or ""
    return ""


def _json(result: dict[str, Any]) -> str:
    # Tool results reach the model as text: send JSON, not a Python repr.
    return json.dumps(result, ensure_ascii=False, default=str)


async def _run_tool(
    services: Services,
    state: QuoteSession,
    name: str,
    args: dict[str, Any],
    run: Awaitable[dict[str, Any]],
    last_said: str | None = None,
) -> str:
    """Run one tool and report it (with its timing and what's on file after) as events.
    ``last_said``: the caller's message, so a question in it is answered first."""
    started = time.perf_counter()
    result: dict[str, Any] | None = None
    try:
        result = _answer_first(name, await run, last_said)
        return _json(result)
    finally:
        events = services.events
        events.tool(name, args, result, (time.perf_counter() - started) * 1000)
        events.state(state.snapshot(), str(state.stage), state.quote)


class Mia(Agent):
    def __init__(
        self,
        services: Services,
        *,
        greeting: str | None = None,
        speak_greeting: bool = False,
        chat_ctx: ChatContext | None = None,
    ) -> None:
        self.services = services
        self.greeting = greeting or pick_greeting()
        self._speak_greeting = speak_greeting
        self._vehicle_lock = asyncio.Lock()
        ctx = chat_ctx or ChatContext()
        # The greeting is always Mia's first line, so the model knows the call already started.
        ctx.add_message(role="assistant", content=self.greeting)
        super().__init__(instructions=INSTRUCTIONS, chat_ctx=ctx)

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings,
    ) -> AsyncIterable[llm.ChatChunk | str]:
        """The model's output for one step, after two guardrails (see guardrails.py):

        - Tool calls on details the caller never said (or an unconfirmed quote) are dropped.
        - In a step that runs a tool, the model's text is dropped too: the next step speaks
          with the tool's result. Otherwise gpt-oss says its line twice.
        - The text that is spoken goes through ``tidy_speech`` (no repeated sentences, one
          question at a time).
        The step's text is held until the step ends; Groq produces a sentence in well under
        100 ms, so the caller doesn't notice.
        """
        state: QuoteSession = self.session.userdata
        said, last_said = grounded_said(chat_ctx), caller_last_said(chat_ctx)
        mia_last = mia_last_said(chat_ctx)
        state.caller_turns = caller_turn_count(chat_ctx)
        state.last_said = last_said
        _note_partial_vehicle(state, last_said)
        held: list[llm.ChatChunk | str] = []
        text, runs_tool, dropped, failed = "", False, [], False
        called: set[str] = set()
        try:
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                if isinstance(chunk, str):
                    text += chunk
                elif isinstance(chunk, llm.ChatChunk) and chunk.delta:
                    text += chunk.delta.content or ""
                    keep = []
                    for call in chunk.delta.tool_calls:
                        reason = guardrails.check_call(
                            call.name, call.arguments, state, said, last_said, mia_last
                        )
                        if reason:
                            dropped.append(
                                {"tool": call.name, "args": call.arguments, "why": reason}
                            )
                        else:
                            keep.append(call)
                    chunk.delta.tool_calls = keep
                    runs_tool = runs_tool or bool(keep)
                    called.update(c.name for c in keep)
                held.append(chunk)
        except Exception as exc:
            # Stage 7 simulation: Groq's "Failed to parse tool call arguments as JSON" (gpt-oss
            # wrote broken JSON) ended 3 of 72 calls after LiveKit's retries. Nothing from the
            # failed step runs; the caller hears the fallback line and the call goes on.
            logger.warning("llm step failed, using the fallback line: %s", exc)
            held, text, runs_tool, failed = [], "", False, True

        logger.debug("llm step: runs_tool=%s dropped=%d text=%r", runs_tool, len(dropped), text)
        if (
            not runs_tool
            and not state.missing
            and not state.quote
            and not state.ended
            and grounding.is_short_yes(last_said)
            and guardrails.is_read_back(mia_last)
            and state.code_ran_once("get_quote")
        ):
            # Sergio's call, 2026-11-11: "Yep" to the read-back, the model didn't call
            # get_quote, and Mia read everything back again.
            held.append(_call_chunk("get_quote", {}))
            runs_tool = True
            logger.info("yes to the read-back; running get_quote")
        route = grounding.route_in(last_said)
        if (
            not failed
            and route
            and not state.origin
            and not state.destination
            and "save_origin_destination" not in called
            and state.code_ran_once("save_origin_destination")
        ):
            # Scenario question_with_route (2026-11-11): with a question in the same message
            # the model answered it and skipped the route 4 times in 5. "from X to Y" in the
            # caller's own words is certain enough to save; the answer comes next (`next`).
            held.append(_call_chunk("save_origin_destination", route))
            runs_tool = True
            called.add("save_origin_destination")
            logger.info("caller gave the route; running save_origin_destination %s", route)
        if (
            not failed
            and not state.quote
            and any(m.startswith("vehicle") for m in state.missing)
            and state.code_ran_once("save_vehicle")
        ):
            for args in await self._vehicles_said(state, last_said, mia_last, held):
                held.append(_call_chunk("save_vehicle", args))
                runs_tool = True
                called.add("save_vehicle")
                logger.info("caller named the vehicle; running save_vehicle %s", args)
        closing = (
            not failed
            and not state.ended
            and state.transfer not in ("pending", "screening", "connected")
            and "end_call" not in called
            and (
                grounding.is_farewell(last_said)
                or (
                    state.quote
                    and grounding.offered_person(mia_last)
                    and grounding.declines(last_said)
                )
            )
        )
        if closing and state.code_ran_once("end_call"):
            # The caller is done: "Cool. Thank you. Bye." (call 97f388f57b75, 2026-11-11: no
            # end_call, Mia read the details back twice), or "No, thanks" to the
            # representative after the quote (Sergio: close the call, no "anything else?").
            # Nothing else the model planned runs; the closing line comes from end_call.
            for chunk in held:
                if isinstance(chunk, llm.ChatChunk) and chunk.delta and chunk.delta.tool_calls:
                    dropped.extend(
                        {"tool": c.name, "args": c.arguments, "why": "the caller is done"}
                        for c in chunk.delta.tool_calls
                    )
                    chunk.delta.tool_calls = []
            held.append(_call_chunk("end_call", {}))
            runs_tool = True
            logger.info("caller is done (%r); running end_call", last_said)
        if (
            not runs_tool
            and state.off_topic == OFF_TOPIC_LIMIT - 1
            and state.off_topic_turns
            and state.off_topic_turns[-1] == state.caller_turns - 1
            and grounding.is_question(last_said)
            and guardrails.check_call("note_off_topic", "{}", state, said, last_said, mia_last)
            is None
            and state.code_ran_once("note_off_topic")
        ):
            # The model often doesn't count the third unrelated question in a row (stage 7
            # simulations; it turned main's CI red on 2026-11-11). Only a question, only right
            # after another counted one, and never one about shipping (the guardrail's check).
            held.append(_call_chunk("note_off_topic", {}))
            runs_tool = True
            logger.info("third off-topic question in a row; running note_off_topic")
        if not runs_tool and dropped and grounding.asks_for_person(last_said):
            # Stage 7 simulation, 2026-11-10: "could you connect me to a live representative?"
            # -> the model called note_off_topic (dropped) and Mia asked for the car again.
            # The caller plainly asked for a person, so that's the call that runs.
            held.append(_call_chunk("request_human", {"reason": "caller asked for a person"}))
            runs_tool = True
            logger.info("dropped-only step on a request for a person; running request_human")
        # Speak only in steps that don't run a tool, and only the tidied text.
        for chunk in held:
            if isinstance(chunk, str):
                continue
            if chunk.delta:
                chunk.delta.content = None
            yield chunk
        if dropped:
            state.dropped_calls.extend(dropped)
            logger.info("guardrail dropped tool calls: %s", dropped)
            for d in dropped:
                self.services.events.dropped(d["tool"], d["args"] or "", d["why"])
        if not runs_tool:
            spoken = guardrails.removal_question(dropped, state, last_said) or (
                guardrails.tidy_speech(text)
            )
            if not spoken and dropped and grounding.is_question(last_said):
                # The caller asked something and the model only tried tools the guardrail
                # dropped: ask again with no tools, so the question gets an answer.
                spoken = guardrails.tidy_speech(await self._words_only(chat_ctx))
                logger.info("dropped-only step on a question; answered: %r", spoken)
            if not spoken and (dropped or failed):
                spoken = guardrails.fallback_line(state)
            spoken = guardrails.honest_read_back(spoken, state)
            spoken = faq.ensure_answer(spoken, last_said) if spoken else spoken
            spoken = guardrails.no_model_again(spoken, state)
            spoken = guardrails.keep_going(spoken, state)
            if spoken and guardrails.is_goodbye(spoken) and not state.ended:
                # She's closing the call without end_call: hang up after this line plays.
                logger.info("goodbye without end_call; hanging up after it")
                state.ended, state.end_reason = True, "mia"
                state.hang_up_after_speech = True
            if spoken:
                yield spoken

    async def _vehicles_said(
        self,
        state: QuoteSession,
        last_said: str,
        mia_last: str,
        held: list[llm.ChatChunk | str],
    ) -> list[dict[str, Any]]:
        """Vehicles the caller fully named in this message that the model didn't save; code
        saves them (the caller's own words make them certain).

        - Several cars in one message: each with its year, make and a catalog model (call
          2cd0a119e59d, 2026-11-11: "Atlanta to Portland with a twenty twenty two Toyota RAV
          four and a two thousand seventeen Honda Civic" -> only the route was saved).
        - One car: the year and make heard so far plus the model right after the make (Sergio's
          call: "twenty twenty one Ford f hundred and fifty" -> "What model is the 2021 Ford?"),
          or the model alone when Mia just asked for it (call 2f6b9240a6da: "Corolla." to "Did
          you mean a Corolla...?" was never saved, so the quote failed)."""
        by_model: list[str] = []  # makes the model's own save_vehicle calls cover this step
        for chunk in held:
            if isinstance(chunk, llm.ChatChunk) and chunk.delta:
                for call in chunk.delta.tool_calls:
                    if call.name in ("save_vehicle", "update_vehicle"):
                        try:
                            make = (json.loads(call.arguments or "{}") or {}).get("make")
                        except ValueError:
                            make = None
                        by_model.append(str(make or "").lower())
        on_file = {
            (v.year, (v.make or "").lower(), (v.model or "").lower()) for v in state.vehicles
        }
        if grounding.makes_named(last_said) >= 2:
            out = []
            for mention in grounding.vehicle_mentions(last_said):
                make, year = mention["make"], mention["year"]
                if make.lower() in by_model:
                    by_model.remove(make.lower())
                    continue
                if not year:
                    continue
                model = await model_from_words(self.services, make, mention["words"])
                if model and (year, make.lower(), model.lower()) not in on_file:
                    out.append({"year": year, "make": make, "model": model})
            return out
        partial = state.partial_vehicle
        if not partial.get("make") or by_model:
            return []
        asked_model = bool(_ASKED_MODEL.search(mia_last))
        model = await model_from_words(self.services, partial["make"], last_said, alone=asked_model)
        if not model:
            return []
        args: dict[str, Any] = {"make": partial["make"], "model": model}
        if partial.get("year"):
            args["year"] = partial["year"]
        return [args]

    async def _words_only(self, chat_ctx: llm.ChatContext) -> str:
        """The model's reply with no tools on offer. Live check, 2026-11-10: STT heard "do
        you do a closed shipping?", the model only called a tool the guardrail dropped, and the
        fallback line repeated the vehicle question, so the FAQ went unanswered.

        One attempt, short timeout, and "" on any error (the caller then gets the fallback
        line): the stage 7 simulations showed gpt-oss calling a tool even with none offered,
        which Groq rejects ("Tool choice is none, but model called a tool"); with LiveKit's
        default retries that crashed the turn after 4 tries."""
        model = self.llm if isinstance(self.llm, llm.LLM) else self.session.llm
        # Without the tool calls in its history gpt-oss stops reaching for tools (the first
        # simulation run: 8 of these retries failed with "model called a tool").
        ctx = chat_ctx.copy(exclude_function_call=True)
        ctx.add_message(role="system", content=ANSWER_ONLY)
        text = ""
        try:
            stream = model.chat(
                chat_ctx=ctx,
                tools=None,
                tool_choice="none",
                conn_options=APIConnectOptions(max_retry=0, timeout=5.0),
            )
            async with stream:
                async for chunk in stream:
                    if chunk.delta:
                        text += chunk.delta.content or ""
        except Exception as exc:
            logger.warning("words-only step failed, using the fallback line: %s", exc)
            return ""
        return text

    async def tts_node(self, text: AsyncIterable[str], model_settings):
        """Numbers become words before any voice reads them (see speech.py)."""

        async def spoken() -> AsyncIterable[str]:
            async for chunk in text:
                yield speech.for_tts(chunk)

        async for frame in Agent.default.tts_node(self, spoken(), model_settings):
            yield frame

    async def on_enter(self) -> None:
        if self._speak_greeting:  # voice: say it without waiting for the LLM
            self.session.say(self.greeting, add_to_chat_ctx=False)
            self.services.events.turn("assistant", self.greeting, kind="greeting")

    @function_tool
    async def save_origin_destination(
        self,
        context: RunContext[QuoteSession],
        origin_city: str | None = None,
        origin_state: str | None = None,
        destination_city: str | None = None,
        destination_state: str | None = None,
    ) -> str:
        """Save where the vehicle ships from and to. Call it as soon as you hear either city.

        Args:
            origin_city: Pickup city, exactly as the caller said it. Omit if not said.
            origin_state: Pickup state, only if the caller said it.
            destination_city: Delivery city, exactly as the caller said it. Omit if not said.
            destination_state: Delivery state, only if the caller said it.
        """
        args = {
            "origin_city": origin_city,
            "origin_state": origin_state,
            "destination_city": destination_city,
            "destination_state": destination_state,
        }
        return await _run_tool(
            self.services,
            context.userdata,
            "save_origin_destination",
            args,
            tools.save_origin_destination(
                context.userdata, self.services, **args, said=grounded_said(self.chat_ctx)
            ),
            last_said=caller_last_said(self.chat_ctx),
        )

    @function_tool
    async def save_vehicle(
        self,
        context: RunContext[QuoteSession],
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        vehicle_type: str | None = None,
        # bool | None: gpt-oss sends null for "not mentioned", and Groq rejects a null
        # boolean (stage 7 simulation: the turn crashed). None means it runs.
        drivable: bool | None = None,
        total_vehicles: int | None = None,
    ) -> str:
        """Save one vehicle. Call once per vehicle with whatever the caller said about it.

        Args:
            year: Model year, only if the caller said it.
            make: Brand, only if the caller said it.
            model: Model, only if the caller said it.
            vehicle_type: Only if they don't know the model or year: sedan, SUV, pickup, van...
            drivable: False only if the caller said the vehicle doesn't run.
            total_vehicles: How many vehicles they're shipping in total, if they said so.
        """
        args = {
            "year": year,
            "make": make,
            "model": model,
            "vehicle_type": vehicle_type,
            "drivable": drivable,
            "total_vehicles": total_vehicles,
        }
        # One at a time, in the order they were called: two saves in one step ran together and
        # the faster lookup became vehicle 1 (live run, 2026-11-11: "a 2025 Honda Civic and a
        # 2020 Toyota 4Runner" was saved Toyota first). asyncio.Lock is first come, first served.
        async with self._vehicle_lock:
            return await _run_tool(
                self.services,
                context.userdata,
                "save_vehicle",
                args,
                tools.save_vehicle(
                    context.userdata,
                    self.services,
                    **args,
                    said=grounded_said(self.chat_ctx),
                    last_said=caller_last_said(self.chat_ctx),
                    unsure=grounding.unsure(caller_last_said(self.chat_ctx))
                    or grounding.offered_types(mia_last_said(self.chat_ctx)),
                ),
                last_said=caller_last_said(self.chat_ctx),
            )

    @function_tool
    async def update_vehicle(
        self,
        context: RunContext[QuoteSession],
        quote_id: str | None = None,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        vehicle_type: str | None = None,
        drivable: bool | None = None,
    ) -> str:
        """Change a vehicle already on file ("actually it's a 2021", "it's a 4Runner, not a
        Civic"). Pass only what the caller changed.

        Args:
            quote_id: The vehicle's quote_id from on_file. Omit if there's only one vehicle.
            year: New model year, only if the caller said it.
            make: New brand, only if the caller said it.
            model: New model, only if the caller said it.
            vehicle_type: Only if they don't know the model: sedan, SUV, pickup, van...
            drivable: False if they now say it doesn't run, True if they say it does.
        """
        args = {
            "quote_id": quote_id,
            "year": year,
            "make": make,
            "model": model,
            "vehicle_type": vehicle_type,
            "drivable": drivable,
        }
        return await _run_tool(
            self.services,
            context.userdata,
            "update_vehicle",
            args,
            tools.update_vehicle(
                context.userdata,
                self.services,
                **args,
                said=grounded_said(self.chat_ctx),
                last_said=caller_last_said(self.chat_ctx),
            ),
            last_said=caller_last_said(self.chat_ctx),
        )

    @function_tool
    async def remove_vehicle(
        self, context: RunContext[QuoteSession], quote_id: str | None = None
    ) -> str:
        """Remove a vehicle the caller is no longer shipping.

        Args:
            quote_id: The vehicle's quote_id from on_file.
        """
        return await _run_tool(
            self.services,
            context.userdata,
            "remove_vehicle",
            {"quote_id": quote_id},
            tools.remove_vehicle(
                context.userdata,
                self.services,
                quote_id=quote_id,
                last_said=caller_last_said(self.chat_ctx),
            ),
        )

    @function_tool
    async def undo_last_change(self, context: RunContext[QuoteSession]) -> str:
        """Put back what the last vehicle or route change replaced, when the caller changes
        their mind back ("actually, keep the Honda")."""
        return await _run_tool(
            self.services,
            context.userdata,
            "undo_last_change",
            {},
            tools.undo_last_change(context.userdata, self.services),
        )

    @function_tool
    async def get_quote(self, context: RunContext[QuoteSession]) -> str:
        """Get the price for every vehicle on file. Only after the caller confirmed the details."""
        return await _run_tool(
            self.services,
            context.userdata,
            "get_quote",
            {},
            tools.get_quote(
                context.userdata, self.services, last_said=caller_last_said(self.chat_ctx)
            ),
        )

    @function_tool
    async def request_human(self, context: RunContext[QuoteSession], reason: str = "") -> str:
        """Connect the caller with a licensed representative (a person). Only when the caller
        asked for one or said yes to your offer.

        Args:
            reason: Short reason, e.g. "wants to talk after quote" or "asked for a human".
        """
        state = context.userdata
        was_pending = state.transfer in ("pending", "connected")
        # A yes right after Mia's offer is an organic transfer; anything else, they asked.
        last, offer = caller_last_said(self.chat_ctx), mia_last_said(self.chat_ctx)
        accepted = grounding.offered_person(offer) and grounding.is_confirmation(last)
        result = await _run_tool(
            self.services,
            state,
            "request_human",
            {"reason": reason},
            tools.request_human(state, self.services, reason=reason, asked=not accepted),
        )
        start = self.services.transfer
        if start and state.transfer == "pending" and not was_pending:
            # Dial once "connecting you" has been spoken (same pattern as end_call).
            context.speech_handle.add_done_callback(lambda _: start())
        return result

    @function_tool
    async def note_off_topic(self, context: RunContext[QuoteSession]) -> str:
        """The caller asked something unrelated to car shipping (a joke, trivia, nonsense).
        Call it before answering, then follow its `next`."""
        return await _run_tool(
            self.services,
            context.userdata,
            "note_off_topic",
            {},
            tools.note_off_topic(context.userdata, self.services),
        )

    @function_tool
    async def end_call(self, context: RunContext[QuoteSession]) -> str:
        """End the call when the caller is done. You'll say goodbye right after."""
        result = await _run_tool(
            self.services,
            context.userdata,
            "end_call",
            {},
            tools.end_call(context.userdata, self.services),
        )
        hang_up = self.services.end_call
        if hang_up:
            # The goodbye is generated from this tool's result and played on the same speech
            # handle (like livekit.agents.beta.tools.EndCallTool), so hang up once it's done.
            context.speech_handle.add_done_callback(lambda _: hang_up())
        return result
