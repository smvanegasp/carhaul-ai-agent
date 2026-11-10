"""The Mia agent: LiveKit function tools over mia.tools, plus the LLM factory."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncIterable, Awaitable
from typing import Any

from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentSession,
    ChatContext,
    RunContext,
    function_tool,
    llm,
)
from livekit.plugins import groq

from mia import grounding, guardrails, speech, tools
from mia.prompt import INSTRUCTIONS, pick_greeting
from mia.state import QuoteSession
from mia.tools import Services

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
    return AgentSession[QuoteSession](
        llm=llm or make_llm(), userdata=state, max_tool_steps=MAX_TOOL_STEPS, **kwargs
    )


def caller_said(chat_ctx: ChatContext) -> str:
    """Everything the caller has said so far (for the grounding guardrail)."""
    return "\n".join(
        item.text_content or ""
        for item in chat_ctx.items
        if getattr(item, "type", None) == "message" and item.role == "user"
    )


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
) -> str:
    """Run one tool and report it (with its timing and what's on file after) as events."""
    started = time.perf_counter()
    result: dict[str, Any] | None = None
    try:
        result = await run
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
        said, last_said = caller_said(chat_ctx), caller_last_said(chat_ctx)
        mia_last = mia_last_said(chat_ctx)
        state.caller_turns = caller_turn_count(chat_ctx)
        held: list[llm.ChatChunk | str] = []
        text, runs_tool, dropped = "", False, []
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
                        dropped.append({"tool": call.name, "args": call.arguments, "why": reason})
                    else:
                        keep.append(call)
                chunk.delta.tool_calls = keep
                runs_tool = runs_tool or bool(keep)
            held.append(chunk)

        logger.debug("llm step: runs_tool=%s dropped=%d text=%r", runs_tool, len(dropped), text)
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
            spoken = guardrails.tidy_speech(text)
            if not spoken and dropped:
                spoken = guardrails.fallback_line(state)
            if spoken and guardrails.is_goodbye(spoken) and not state.ended:
                # She's closing the call without end_call: hang up after this line plays.
                logger.info("goodbye without end_call; hanging up after it")
                state.ended, state.end_reason = True, "mia"
                state.hang_up_after_speech = True
            if spoken:
                yield spoken

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
                context.userdata, self.services, **args, said=caller_said(self.chat_ctx)
            ),
        )

    @function_tool
    async def save_vehicle(
        self,
        context: RunContext[QuoteSession],
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        vehicle_type: str | None = None,
        drivable: bool = True,
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
        return await _run_tool(
            self.services,
            context.userdata,
            "save_vehicle",
            args,
            tools.save_vehicle(
                context.userdata, self.services, **args, said=caller_said(self.chat_ctx)
            ),
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
