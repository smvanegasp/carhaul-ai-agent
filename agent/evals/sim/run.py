"""Run the simulations: every persona x path, Mia against a simulated caller, fake CarHauler
and geocoder (no CarHauler calls, no Google calls: only Groq).

    cd agent
    uv run python -m evals.sim.run                      # everything once (72 calls)
    uv run python -m evals.sim.run --paths SHP,QHP --personas G_P_V --repeat 3
    uv run python -m evals.sim.run --scenario-runs 3    # also the scenario suite, 3 times

Each run leaves a folder in ``evals/simulations/runs/`` (transcripts, report, summary) and
refreshes ``evals/simulations/README.md``. Models: ``MIA_LLM_MODEL`` for Mia,
``SIM_CALLER_MODEL`` for the caller.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

AGENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT / "tests"))  # the fake APIs live with the tests

import respx  # noqa: E402
from fake_carhauler import BASE, FakeCarHauler  # noqa: E402
from fake_geo import fake_city_to_zip  # noqa: E402
from livekit.agents import FunctionCall, FunctionCallOutput  # noqa: E402
from livekit.agents.llm import ChatMessage  # noqa: E402

from evals.sim import report  # noqa: E402
from evals.sim.caller import DEFAULT_NOTE, Caller  # noqa: E402
from evals.sim.catalog import PATH_CODES, Fragment, Plan, build_plan, path  # noqa: E402
from mia.agent import DEFAULT_MODEL, Mia, new_session  # noqa: E402
from mia.carhauler import CarHaulerClient  # noqa: E402
from mia.prompt import GREETINGS  # noqa: E402
from mia.state import QuoteSession  # noqa: E402
from mia.tools import Services  # noqa: E402
from mia.vehicles import VehicleResolver  # noqa: E402

RUNS_DIR = AGENT / "evals" / "simulations" / "runs"
MAX_TURNS = 20
# Groq allows 250k tokens a minute on this account; 4 calls at once hit it (first run: 18 of
# 72 calls failed with a 429). A call that hits it waits and starts over.
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_WAIT_S = 30


def scrub(error: str) -> str:
    """Errors go into public transcripts: no account or request IDs."""
    error = re.sub(r"\borg_[A-Za-z0-9]+", "org_…", error)
    error = re.sub(r"\breq_[A-Za-z0-9]+", "req_…", error)
    return error[:300]


def rate_limited(record: dict) -> bool:
    return bool(record["error"]) and ("429" in record["error"] or "Rate limit" in record["error"])


# --- one conversation ------------------------------------------------------------------------


def trigger(state: QuoteSession) -> str:
    """Where the call is, for the fragments (catalog.py)."""
    if state.quote:
        return "after_quote"
    if not state.origin and not state.destination:
        return "route"
    if not state.vehicles:
        return "vehicle"
    return "read_back" if not state.missing else "vehicle"


ORDER = {"route": 0, "vehicle": 1, "read_back": 2, "after_quote": 3}


def due(frag: Fragment, where: str) -> bool:
    """A fragment fires at its trigger, or at the next turn if the call went past it (a
    generous caller gives the car with the route, so "vehicle" never comes). A change after the
    quote waits for a quote."""
    if frag.trigger == "after_quote":
        return where == "after_quote"
    return ORDER[where] >= ORDER[frag.trigger]


def note_for(frag: Fragment, truth: dict[str, Any]) -> str:
    """The director's note for a fragment; changes also update the ground truth."""
    if frag.kind == "faq":
        return (
            f'Before anything else, ask Mia this, in your own words: "{frag.text}" Don\'t give '
            "any new details in this turn."
        )
    if frag.kind == "off_topic":
        return (
            f'Ask Mia something unrelated to car shipping, like: "{frag.text}" Don\'t give any '
            "shipping details in this turn."
        )
    if frag.kind == "correction":
        year = truth["vehicles"][0].split()[0]
        return (
            "Mia is asking about the car: give its details. When you say the year, first say a "
            "wrong year and correct yourself in the same sentence, like 'a twenty ten... no "
            f"sorry, twenty twenty'. The right year is {year}."
        )
    if frag.kind == "change_vehicle":
        old = truth["vehicles"][0]
        truth["vehicles"][0] = frag.text
        return (
            f"Tell Mia you made a mistake: the car is actually a {frag.text}, not the {old}. "
            "Don't answer anything else yet."
        )
    if frag.kind == "change_route":
        old = truth["destination"]
        truth["destination"] = frag.text
        return f"Tell Mia the car is actually going to {frag.text}, not {old}."
    if frag.kind == "person":
        return "Instead of answering, ask to speak with a real person."
    raise ValueError(frag.kind)


END_NOTES = {
    "decline": (
        "Mia gave you the price. Say no thanks to talking with a representative, thank her and "
        "say goodbye."
    ),
    "accept": "Mia gave you the price. Say yes, you'd like to talk to a licensed representative.",
}


def _final(state: QuoteSession) -> dict[str, Any]:
    snap = state.snapshot()
    quote = state.quote or {}
    return {
        "origin": snap["origin"],
        "destination": snap["destination"],
        "vehicles": [v["vehicle"] for v in snap["vehicles"]],
        "quote_total": quote.get("total"),
        # The quote's items are spoken labels ("the Toyota"), so it's matched by quote ID.
        "quote_ids": sorted(v["quote_id"] for v in quote.get("per_vehicle", [])),
        "vehicle_ids": sorted(v.quote_id for v in state.vehicles),
        "ended": state.ended,
        "end_reason": state.end_reason,
        "transfer": state.transfer,
        "transfer_kind": state.transfer_kind,
        "human_requested": state.human_requested,
        "off_topic": state.off_topic,
        "trash": len(state.trash),
    }


async def converse(
    plan: Plan, services: Services, caller: Caller, n: int = 0, mia_llm=None
) -> dict:
    """One simulated call; returns its record (scored by ``score``)."""
    state = QuoteSession()
    agent = Mia(services, greeting=GREETINGS[n % len(GREETINGS)])
    truth = {
        "origin": plan.case.origin.label,
        "destination": plan.case.destination.label,
        "vehicles": list(plan.case.vehicles),
    }
    pending = list(plan.fragments)
    fired: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "id": plan.id,
        "persona": plan.persona.code,
        "path": plan.path.code,
        "family": plan.path.family,
        "case": {
            "origin": plan.case.origin.label,
            "destination": plan.case.destination.label,
            "vehicles": list(plan.case.vehicles),
        },
        "greeting": agent.greeting,
        "turns": turns,
        "fragments": fired,
        "planned_fragments": [f.kind for f in plan.fragments],
        "error": None,
    }
    outcome, usage = "too_long", {}
    try:
        async with new_session(state, llm=mia_llm) as session:
            await session.start(agent)
            mia_said, end_note = agent.greeting, False
            for turn_n in range(1, MAX_TURNS + 1):
                where = trigger(state)
                for late in [f for f in pending if f.kind == "correction" and state.vehicles]:
                    pending.remove(late)  # the car is on file: nothing left to correct
                    fired.append(
                        {"kind": late.kind, "text": "", "turn": None, "words": [], "skipped": True}
                    )
                frag = next((f for f in pending if due(f, where)), None)
                if frag:
                    pending.remove(frag)
                    note, kind = note_for(frag, truth), frag.kind
                    fired.append(
                        {
                            "kind": frag.kind,
                            "text": frag.text,
                            "turn": turn_n,
                            "words": frag.expect_words,
                        }
                    )
                elif state.quote and not any(f.trigger == "after_quote" for f in pending):
                    note, kind, end_note = END_NOTES[plan.path.end], f"end_{plan.path.end}", True
                else:
                    note, kind = DEFAULT_NOTE, "answer"
                if where == "vehicle" and len(truth["vehicles"]) > 1 and kind != "person":
                    n_cars = len(truth["vehicles"])
                    note += f" Remember you're shipping {n_cars} cars: make sure Mia knows."
                line = await caller.reply(mia_said, note)
                dropped_before = len(state.dropped_calls)
                started = time.perf_counter()
                result = await session.run(user_input=line)
                ms = round((time.perf_counter() - started) * 1000)
                outputs = {
                    e.item.call_id: e.item.output
                    for e in result.events
                    if isinstance(e.item, FunctionCallOutput)
                }
                tools_run, said = [], []
                for ev in result.events:
                    item = ev.item
                    if isinstance(item, FunctionCall):
                        out = outputs.get(item.call_id, "")
                        tools_run.append(
                            {"name": item.name, "args": item.arguments, "ok": '"ok": true' in out}
                        )
                    elif isinstance(item, ChatMessage) and item.role == "assistant":
                        said.append(item.text_content or "")
                mia_said = " ".join(s for s in said if s) or "(says nothing)"
                turns.append(
                    {
                        "n": turn_n,
                        "note": kind,
                        "caller": line,
                        "mia": mia_said,
                        "tools": tools_run,
                        "dropped": state.dropped_calls[dropped_before:],
                        "ms": ms,
                    }
                )
                if state.transfer in ("pending", "connected"):
                    outcome = "transferred"
                    break
                if state.ended:
                    outcome = "off_topic_end" if state.end_reason == "off_topic" else "ended"
                    break
                if end_note:
                    outcome = "caller_done"
                    break
            usage = _usage(session)
    except Exception as exc:  # an API error: recorded, never stops the run
        outcome, record["error"] = "error", scrub(f"{type(exc).__name__}: {exc}")
    record.update(
        outcome=outcome,
        truth=truth,
        final=_final(state),
        dropped_calls=len(state.dropped_calls),
        usage={**usage, "caller_in": caller.input_tokens, "caller_out": caller.output_tokens},
    )
    record["checks"] = score(record)
    record["passed"] = all(record["checks"].values())
    return record


def _usage(session) -> dict[str, int]:
    mia_in = mia_out = 0
    try:
        for u in session.usage.model_usage:
            mia_in += getattr(u, "input_tokens", 0) or 0
            mia_out += getattr(u, "output_tokens", 0) or 0
    except Exception:  # usage is a nice-to-have
        pass
    return {"mia_in": mia_in, "mia_out": mia_out}


# --- scoring ---------------------------------------------------------------------------------


def _mentions(text: str, groups: list[list[str]]) -> bool:
    text = text.lower()
    return all(any(w in text for w in group) for group in groups)


def score(record: dict[str, Any]) -> dict[str, bool]:
    """Pass/fail checks for one call, from its record alone (so old runs can be re-scored)."""
    spec = path(record["path"])
    final, truth = record["final"], record["truth"]
    mia_text = " ".join(t["mia"] for t in record["turns"])
    checks: dict[str, bool] = {"no_error": record["error"] is None}
    checks["finished"] = record["outcome"] not in ("too_long", "error")
    if spec.expect_quote:
        total = final["quote_total"]
        checks["quoted"] = total is not None
        checks["route"] = (final["origin"], final["destination"]) == (
            truth["origin"],
            truth["destination"],
        )
        checks["vehicles"] = sorted(final["vehicles"]) == sorted(truth["vehicles"])
        checks["quote_matches"] = total is not None and final["quote_ids"] == final["vehicle_ids"]
        checks["price_spoken"] = total is not None and f"${total:,}" in mia_text
    else:
        checks["no_quote"] = final["quote_total"] is None
    if spec.expect_transfer:
        checks["transferred"] = final["transfer"] in ("pending", "connected")
    else:
        checks["no_transfer"] = final["transfer"] is None
    if spec.expect_off_topic_end:
        checks["off_topic_end"] = final["end_reason"] == "off_topic"
    else:
        checks["not_cut_off"] = final["end_reason"] != "off_topic"
    expected = len(record["planned_fragments"])
    checks["fragments_fired"] = len(record["fragments"]) >= expected
    faqs = [f for f in record["fragments"] if f["kind"] == "faq"]
    if faqs:
        by_turn = {t["n"]: t["mia"] for t in record["turns"]}
        checks["faq_answered"] = all(
            _mentions(by_turn.get(f["turn"], ""), f["words"]) for f in faqs
        )
    # A skipped fragment is the simulation's, not Mia's: it counts as done.
    return checks


# --- the run ---------------------------------------------------------------------------------


async def simulate(plans: list[Plan], concurrency: int = 2) -> list[dict]:
    fake = FakeCarHauler()
    records: list[dict] = []
    with respx.mock(assert_all_called=False) as router:
        router.route(url__startswith=BASE).mock(side_effect=fake.handler)
        router.route().pass_through()  # Groq
        client = CarHaulerClient(api_key="test-key", base_url=BASE, retry_wait=0)
        resolver = VehicleResolver(client)
        gate = asyncio.Semaphore(concurrency)

        async def one(n: int, plan: Plan) -> None:
            async with gate:
                services = Services(
                    carhauler=client,
                    resolver=resolver,
                    geocode=fake_city_to_zip,
                    transfer=lambda: None,  # a transfer starts; the call is scored there
                )
                started = time.perf_counter()
                for attempt in range(RATE_LIMIT_RETRIES + 1):
                    rec = await converse(plan, services, Caller(plan), n)
                    if not rate_limited(rec) or attempt == RATE_LIMIT_RETRIES:
                        break
                    print(f"      {plan.id}: rate limited, again in {RATE_LIMIT_WAIT_S} s")
                    await asyncio.sleep(RATE_LIMIT_WAIT_S)
                rec["attempts"] = attempt + 1
                rec["seconds"] = round(time.perf_counter() - started, 1)
                records.append(rec)
                mark = "PASS" if rec["passed"] else "FAIL"
                failed = [k for k, v in rec["checks"].items() if not v]
                print(
                    f"[{len(records):>3}/{len(plans)}] {mark} {plan.id} ({rec['outcome']})"
                    + (f" failed: {', '.join(failed)}" if failed else ""),
                    flush=True,
                )

        try:
            await asyncio.gather(*(one(n, p) for n, p in enumerate(plans)))
        finally:
            await client.aclose()
    order = {p.id: i for i, p in enumerate(plans)}
    return sorted(records, key=lambda r: order[r["id"]])


def scenario_rates(runs: int) -> dict[str, dict[str, int]]:
    """Run the scenario suite (tests/test_scenarios.py) ``runs`` times; passes per scenario.
    This is where the known flaky ones (faq_mid_call, off_topic_three_strikes,
    happy_path_ngc_3v) get a pass rate instead of a red CI now and then."""
    rates: dict[str, dict[str, int]] = {}
    for i in range(runs):
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "junit.xml"
            print(f"scenario suite, run {i + 1}/{runs}...", flush=True)
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-m",
                    "llm",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"--junitxml={junit}",
                ],
                cwd=AGENT,
                capture_output=True,
                text=True,
                check=False,
            )
            if not junit.exists():
                continue
            for case in ET.parse(junit).getroot().iter("testcase"):
                name = case.get("name", "")
                if "[" not in name:
                    continue
                sid = name.split("[", 1)[1].rstrip("]")
                bad = case.find("failure") is not None or case.find("error") is not None
                skipped = case.find("skipped") is not None
                if skipped:
                    continue
                r = rates.setdefault(sid, {"runs": 0, "passed": 0})
                r["runs"] += 1
                r["passed"] += 0 if bad else 1
    return rates


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--personas", help="comma-separated codes, e.g. G_C_V,NG_P_NV")
    ap.add_argument("--paths", help=f"comma-separated: {','.join(PATH_CODES)}")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--limit", type=int, help="only the first N calls (a quick check)")
    ap.add_argument("--scenario-runs", type=int, default=0)
    ap.add_argument("--label", default="manual", help="e.g. manual, or the change being checked")
    ap.add_argument("--out", type=Path, default=RUNS_DIR)
    args = ap.parse_args(argv)

    load_dotenv(AGENT.parent / ".env")
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set", file=sys.stderr)
        return 2
    split = lambda s: [x.strip() for x in s.split(",") if x.strip()] if s else None  # noqa: E731
    plans = build_plan(split(args.personas), split(args.paths), args.repeat)
    if args.limit:
        plans = plans[: args.limit]
    started = datetime.now(UTC)
    mia_model = os.getenv("MIA_LLM_MODEL") or DEFAULT_MODEL
    caller_model = Caller.__dataclass_fields__["model"].default_factory()
    print(f"{len(plans)} simulated calls; Mia {mia_model}, caller {caller_model}", flush=True)
    records = asyncio.run(simulate(plans, args.concurrency))
    rates = scenario_rates(args.scenario_runs) if args.scenario_runs else {}
    meta = {
        "started": started.isoformat(timespec="seconds"),
        "minutes": round((datetime.now(UTC) - started).total_seconds() / 60, 1),
        "label": args.label,
        "mia_model": mia_model,
        "caller_model": caller_model,
        "commit": _git_sha(),
    }
    folder = report.write_run(args.out, meta, records, rates)
    report.write_index(args.out)
    s = report.summarize(meta, records, rates)
    print(f"\n{s['passed']}/{s['n']} passed ({s['pass_rate']:.0%}); report: {folder / 'report.md'}")
    return 0


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=AGENT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
