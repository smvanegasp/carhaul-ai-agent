"""Scenario tests: replay the reference conversations (evals/scenarios/*.yaml) against the real
LLM, with the fake CarHauler API and a fake geocoder (deterministic prices, no paid APIs).

Run:   cd agent && uv run pytest -m llm -v -s
Model: MIA_LLM_MODEL (default openai/gpt-oss-20b); the judge is MIA_JUDGE_MODEL
       (default openai/gpt-oss-120b).

Each turn can check:
  on_file   what's saved after the turn (origin, destination, vehicle labels)
  tools     tools that must be called this turn
  no_tools  tools that must not be called this turn
  says      exact strings Mia must say (prices come from code, so they must match)
  judge     an LLM judge checks Mia's last message against this intent

Tool calls the guardrail dropped (invented details, unconfirmed quote) are allowed but printed:
they show where the model tried to invent details.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv
from fake_geo import fake_city_to_zip
from livekit.agents import FunctionCall, FunctionCallOutput
from livekit.agents.llm import ChatMessage

from mia.agent import Mia, make_llm, new_session
from mia.prompt import GREETINGS
from mia.state import QuoteSession
from mia.tools import Services

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
SCENARIOS = sorted((Path(__file__).resolve().parents[1] / "evals" / "scenarios").glob("*.yaml"))

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="GROQ_API_KEY not set"),
]


def _check_on_file(expected: dict, state: QuoteSession, where: str) -> None:
    snap = state.snapshot()
    for key, want in expected.items():
        if key == "vehicles":
            got = [v["vehicle"] for v in snap["vehicles"]]
        else:
            got = snap[key]
        assert got == want, f"{where}: on_file.{key} is {got!r}, expected {want!r}"


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
async def test_scenario(path, client, resolver):
    scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    state = QuoteSession()
    judge = make_llm(os.getenv("MIA_JUDGE_MODEL") or "openai/gpt-oss-120b")
    agent = Mia(services, greeting=GREETINGS[0])
    print(f"\n=== {scenario['id']} ({scenario.get('persona')}, {scenario.get('path')})")
    print(f"Mia: {agent.greeting}")

    async with new_session(state) as session:
        await session.start(agent)
        for n, turn in enumerate(scenario["turns"], 1):
            where = f"{scenario['id']} turn {n}"
            print(f"You: {turn['user']}")
            dropped_before = len(state.dropped_calls)
            started = time.perf_counter()
            result = await session.run(user_input=turn["user"])
            print(f"     ({(time.perf_counter() - started) * 1000:.0f} ms)")
            for d in state.dropped_calls[dropped_before:]:
                print(f"     DROPPED -> {d['tool']}({d['args']})  [{d['why']}]")

            called, refused, said, last_msg = [], [], [], None
            outputs = [e.item for e in result.events if isinstance(e.item, FunctionCallOutput)]
            for i, ev in enumerate(result.events):
                item = ev.item
                if isinstance(item, FunctionCall):
                    out = next((o for o in outputs if o.call_id == item.call_id), None)
                    ok = bool(out) and '"ok": true' in out.output
                    # Only successful calls count; a tool refusing (e.g. NOT_CONFIRMED) is fine.
                    (called if ok else refused).append(item.name)
                    tag = "" if ok else "REFUSED "
                    print(f"     {tag}-> {item.name}({item.arguments})")
                elif isinstance(item, ChatMessage) and item.role == "assistant":
                    said.append(item.text_content or "")
                    last_msg = i
                    print(f"Mia: {item.text_content}")
            text = " ".join(said)

            expect = turn.get("expect") or {}
            if "on_file" in expect:
                _check_on_file(expect["on_file"], state, where)
            for name in expect.get("tools", []):
                assert name in called, f"{where}: expected a {name} call, got {called}"
            for name in expect.get("no_tools", []):
                assert name not in called, f"{where}: {name} must not be called yet"
            for phrase in expect.get("says", []):
                assert phrase in text, f"{where}: Mia should say {phrase!r}; said {text!r}"
            if "judge" in expect:
                assert last_msg is not None, f"{where}: Mia said nothing"
                await (
                    result.expect[last_msg]
                    .is_message(role="assistant")
                    .judge(judge, intent=expect["judge"])
                )

    truth = scenario["ground_truth"]
    _check_on_file(
        {
            "origin": truth["origin"],
            "destination": truth["destination"],
            "vehicles": truth["vehicles"],
        },
        state,
        f"{scenario['id']} ground truth",
    )
