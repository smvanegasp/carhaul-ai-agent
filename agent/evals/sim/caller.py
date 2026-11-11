"""The simulated caller: a model (Groq, ``SIM_CALLER_MODEL``, default gpt-oss-120b) playing a
persona with a ground truth. The runner adds a director's note to each of Mia's lines (what to
do this turn: answer, ask an FAQ, change the car...); the persona decides how it's said."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from evals.sim.catalog import Plan

DEFAULT_CALLER_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1"

DEFAULT_NOTE = (
    "Reply to Mia in character. Answer what she asked; volunteer more only if your persona "
    "does. If she reads your details back and they're right, confirm them."
)


def system_prompt(plan: Plan) -> str:
    case = plan.case
    cars = " and ".join(case.vehicles)
    count = "one car" if len(case.vehicles) == 1 else f"{len(case.vehicles)} cars"
    return (
        "You are role-playing a person on a phone call with Mia, F&F's virtual assistant, to "
        "get a quote for shipping your car. This is a test of Mia, so stay in character.\n\n"
        f"Your facts (never invent others): you're shipping {count}: {cars}, from "
        f"{case.origin.label} to {case.destination.label}. It runs fine. If Mia asks something "
        "you don't know, say you're not sure."
        + (
            " When you talk about the cars, make sure Mia knows you have more than one, and "
            "give each one when she asks."
            if len(case.vehicles) > 1
            else ""
        )
        + "\n\n"
        f"How you talk: {plan.persona.describe()}\n\n"
        "Each message from Mia comes with a note in [brackets] from the test director: follow "
        "it, and never mention it. Write only the words you say out loud, as a phone caller "
        "would: no quotes, no stage directions, no markdown, no emoji."
    )


@dataclass
class Caller:
    plan: Plan
    model: str = field(default_factory=lambda: os.getenv("SIM_CALLER_MODEL", DEFAULT_CALLER_MODEL))
    client: AsyncOpenAI | None = None
    history: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        self.client = self.client or AsyncOpenAI(
            base_url=GROQ_URL, api_key=os.environ["GROQ_API_KEY"], max_retries=4
        )
        self.history = [{"role": "system", "content": system_prompt(self.plan)}]

    async def reply(self, mia_said: str, note: str = DEFAULT_NOTE) -> str:
        """The caller's next line after Mia's (the conversation is kept here)."""
        self.history.append({"role": "user", "content": f"Mia: {mia_said}\n\n[{note}]"})
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=self.history,
            temperature=0.9,
            max_tokens=400,
            **({"reasoning_effort": "low"} if "gpt-oss" in self.model else {}),
        )
        if resp.usage:
            self.input_tokens += resp.usage.prompt_tokens or 0
            self.output_tokens += resp.usage.completion_tokens or 0
        line = clean(resp.choices[0].message.content or "") or "Sorry, could you say that again?"
        self.history.append({"role": "assistant", "content": line})
        return line


def clean(text: str) -> str:
    """Only the spoken words: no 'Caller:' prefix, quotes or bracketed directions."""
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", text)
    text = re.sub(r"^\s*(?:caller|me|you)\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip().strip('"“”').strip()
