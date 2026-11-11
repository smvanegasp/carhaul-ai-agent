"""A scripted LLM for offline tests of ``Mia.llm_node``: each model step answers from a script
instead of Groq, so a guardrail path can be reproduced exactly (LiveKit ships no fake LLM).

    llm = ScriptedLLM([Step(calls=[("save_vehicle", "{}")]), Step(text="We only quote open.")])

Every step records whether tools were offered, so a test can check that a retry ran without
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from livekit.agents import APIError, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS


@dataclass
class Step:
    text: str = ""
    calls: list[tuple[str, str]] = field(default_factory=list)  # (tool name, JSON arguments)
    error: str = ""  # the step fails with this message (e.g. Groq rejecting a tool call)


class _Stream(llm.LLMStream):
    def __init__(self, owner: ScriptedLLM, step: Step, **kwargs) -> None:
        super().__init__(owner, **kwargs)
        self._step = step

    async def _run(self) -> None:
        n = len(self._llm.calls)
        if self._step.error:
            raise APIError(self._step.error, retryable=False)
        delta = llm.ChoiceDelta(
            role="assistant",
            content=self._step.text or None,
            tool_calls=[
                llm.FunctionToolCall(name=name, arguments=args, call_id=f"call_{n}_{i}")
                for i, (name, args) in enumerate(self._step.calls)
            ],
        )
        self._event_ch.send_nowait(llm.ChatChunk(id=f"step_{n}", delta=delta))


class ScriptedLLM(llm.LLM):
    def __init__(self, steps: list[Step]) -> None:
        super().__init__()
        self.steps = list(steps)
        self.calls: list[dict] = []  # one per model step: {"tools": number of tools offered}
        self.contexts: list = []  # the chat context each step saw

    def chat(
        self,
        *,
        chat_ctx,
        tools=None,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
        **kwargs,
    ) -> llm.LLMStream:
        step = self.steps.pop(0) if self.steps else Step()
        self.contexts.append(chat_ctx)
        self.calls.append({"tools": len(tools or []), "tool_choice": kwargs.get("tool_choice")})
        return _Stream(self, step, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)
