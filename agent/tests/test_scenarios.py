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
  ended     true if the call must be over after this turn (Mia said goodbye)

A turn can also set ``fail_carhauler: [402, ...]``: the fake CarHauler API answers those
status codes first (an outage at that point of the call; stage 8 error paths).

Real APIs (Sergio, 2026-11-11: we can't control CarHauler or Google, so test against them):

    MIA_SCENARIOS_LIVE=1 uv run pytest -m llm -s

uses the real CarHauler API (catalog from the shared snapshot, so lookups are mostly free) and
Google geocoding. Prices change weekly, so a ``says: ["$..."]`` becomes "says the price this
quote returned". Outage scenarios (``fail_carhauler``) are skipped. Every CarHauler request
is counted and printed: **each quote spends the allowance**, so it runs locally before a PR,
never in CI.

Tool calls the guardrail dropped (invented details, unconfirmed quote) are allowed but printed:
they show where the model tried to invent details.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import pytest
import yaml
from dotenv import load_dotenv
from fake_geo import fake_city_to_zip
from livekit.agents import FunctionCall, FunctionCallOutput
from livekit.agents.llm import ChatMessage

from mia import catalog
from mia.agent import Mia, make_llm, new_session
from mia.carhauler import CarHaulerClient
from mia.geo import city_to_zip
from mia.prompt import GREETINGS
from mia.state import QuoteSession
from mia.tools import Services
from mia.vehicles import VehicleResolver

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


LIVE = os.getenv("MIA_SCENARIOS_LIVE") == "1"
CARHAULER_REQUESTS = {"n": 0}  # real API requests this session (live mode)


async def _live_services() -> tuple[Services, CarHaulerClient]:
    """Real CarHauler (seeded with the catalog snapshot) and real geocoding, with every
    CarHauler request counted."""
    client = CarHaulerClient()
    snapshot = catalog.warm()
    client.seed_cache(snapshot["cache"])
    original = client._get_once

    async def counted(path_: str, params: dict) -> object:
        CARHAULER_REQUESTS["n"] += 1
        if "quote" in path_:
            CARHAULER_REQUESTS["quoted_at"] = time.time()
        return await original(path_, params)

    client._get_once = counted  # type: ignore[method-assign]
    resolver = VehicleResolver(client, model_index=snapshot["index"])
    return Services(carhauler=client, resolver=resolver, geocode=city_to_zip), client


@pytest.mark.skipif(LIVE, reason="MIA_SCENARIOS_LIVE=1: test_scenario_live runs instead")
@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
async def test_scenario(path, client, resolver, fake_api):
    scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = Services(carhauler=client, resolver=resolver, geocode=fake_city_to_zip)
    await _run_scenario(scenario, services, fake_api)


@pytest.mark.skipif(not LIVE, reason="real APIs: set MIA_SCENARIOS_LIVE=1")
@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
async def test_scenario_live(path):
    scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
    if any(t.get("fail_carhauler") for t in scenario["turns"]):
        pytest.skip("simulated outage: fake API only")
    if CARHAULER_REQUESTS.get("quoted_at"):
        # The quote endpoint has a per-minute cap (a 2-car quote 15 s after the last scenario
        # stayed rate-limited for 20 s, 2026-11-11): pace scenarios like real callers, so the
        # previous scenario's quotes don't count against this one.
        await asyncio.sleep(max(0.0, 30 - (time.time() - CARHAULER_REQUESTS["quoted_at"])))
    services, client = await _live_services()
    before = CARHAULER_REQUESTS["n"]
    try:
        await _run_scenario(scenario, services, None)
    finally:
        print(
            f"     [CarHauler requests: {CARHAULER_REQUESTS['n'] - before} this scenario, "
            f"{CARHAULER_REQUESTS['n']} so far]"
        )
        await client.aclose()


async def _run_scenario(scenario: dict, services: Services, fake_api) -> None:
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
            for code in turn.get("fail_carhauler", []):
                fake_api.fail_next(httpx.Response(code, json={"error": f"simulated {code}"}))
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
                    code = ""
                    if out and not ok:
                        try:
                            code = " [" + str(json.loads(out.output).get("error_code")) + "]"
                        except ValueError:
                            pass
                    print(f"     {tag}-> {item.name}({item.arguments}){code}")
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
            if "ended" in expect:
                assert state.ended == expect["ended"], f"{where}: ended is {state.ended}"
            for name in expect.get("no_tools", []):
                assert name not in called, f"{where}: {name} must not be called yet"
            for phrase in expect.get("says", []):
                if LIVE and phrase.startswith("$"):
                    # Real prices change weekly: the price this quote returned.
                    assert state.quote, f"{where}: no quote to say"
                    phrase = f"${state.quote['total']:,}"
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
