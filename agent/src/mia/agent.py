"""The Mia agent: LiveKit function tools over mia.tools, plus the LLM factory."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterable
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

from mia import guardrails, tools
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


def caller_last_said(chat_ctx: ChatContext) -> str:
    """The caller's latest message."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and item.role == "user":
            return item.text_content or ""
    return ""


def _json(result: dict[str, Any]) -> str:
    # Tool results reach the model as text: send JSON, not a Python repr.
    return json.dumps(result, ensure_ascii=False, default=str)


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
                        call.name, call.arguments, state, said, last_said
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
        if not runs_tool:
            speech = guardrails.tidy_speech(text)
            if not speech and dropped:
                speech = guardrails.fallback_line(state)
            if speech:
                yield speech

    async def on_enter(self) -> None:
        if self._speak_greeting:  # voice: say it without waiting for the LLM
            self.session.say(self.greeting, add_to_chat_ctx=False)

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
        return _json(
            await tools.save_origin_destination(
                context.userdata,
                self.services,
                origin_city=origin_city,
                origin_state=origin_state,
                destination_city=destination_city,
                destination_state=destination_state,
                said=caller_said(self.chat_ctx),
            )
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
        return _json(
            await tools.save_vehicle(
                context.userdata,
                self.services,
                year=year,
                make=make,
                model=model,
                vehicle_type=vehicle_type,
                drivable=drivable,
                total_vehicles=total_vehicles,
                said=caller_said(self.chat_ctx),
            )
        )

    @function_tool
    async def get_quote(self, context: RunContext[QuoteSession]) -> str:
        """Get the price for every vehicle on file. Only after the caller confirmed the details."""
        return _json(
            await tools.get_quote(
                context.userdata, self.services, last_said=caller_last_said(self.chat_ctx)
            )
        )

    @function_tool
    async def request_human(self, context: RunContext[QuoteSession], reason: str = "") -> str:
        """Connect the caller with Sergio (a person).

        Args:
            reason: Short reason, e.g. "wants to talk after quote" or "asked for a human".
        """
        return _json(await tools.request_human(context.userdata, self.services, reason=reason))

    @function_tool
    async def end_call(self, context: RunContext[QuoteSession]) -> str:
        """End the call when the caller is done. You'll say goodbye right after."""
        result = await tools.end_call(context.userdata, self.services)
        hang_up = self.services.end_call
        if hang_up:
            # The goodbye is generated from this tool's result and played on the same speech
            # handle (like livekit.agents.beta.tools.EndCallTool), so hang up once it's done.
            context.speech_handle.add_done_callback(lambda _: hang_up())
        return _json(result)
