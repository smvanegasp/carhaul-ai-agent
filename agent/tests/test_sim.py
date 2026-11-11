"""Stage 7 simulator (evals/sim/), offline: the plan, a scripted call end to end, scoring and
the files a run leaves."""

from __future__ import annotations

import json

from fake_carhauler import MAKES, MODELS
from fake_geo import CITIES, fake_city_to_zip
from scripted_llm import ScriptedLLM, Step

from evals.sim import report
from evals.sim.caller import clean
from evals.sim.catalog import CASES, NEW_DESTINATIONS, NEW_VEHICLES, PATHS, PERSONAS, build_plan
from evals.sim.run import converse, score
from mia.tools import Services


def test_every_persona_meets_every_path():
    plans = build_plan()
    assert len(PERSONAS) == 8 and len(plans) == 8 * len(PATHS)
    assert len({p.id for p in plans}) == len(plans)
    assert {p.persona.code for p in plans} >= {"NG_C_NV", "G_P_V"}
    assert len(build_plan(paths=["SHP"], repeat=3)) == 24


def test_ground_truths_are_quotable_offline():
    # Every city and vehicle in a plan must exist in the fakes, or a "failure" is the test's.
    known = {(MAKES[m], name) for m, models in MODELS.items() for name in models.values()}
    vehicles = {v for c in CASES for v in c.vehicles} | set(NEW_VEHICLES)
    for v in vehicles:
        year, make, model = v.split(" ", 2)
        assert (make, model) in known and 2015 <= int(year) <= 2025, v
    places = {p for c in CASES for p in (c.origin, c.destination)} | set(NEW_DESTINATIONS)
    for place in places:
        assert place.city.lower() in CITIES
        assert fake_city_to_zip(place.city, place.state)["state_name"] == place.state


def test_caller_lines_are_only_spoken_words():
    assert clean('Caller: "Sure, let\'s go." [smiles]') == "Sure, let's go."
    assert clean("*laughs* It's a Honda (I think).") == "It's a Honda ."


class ScriptedCaller:
    input_tokens = output_tokens = 0

    def __init__(self, lines):
        self.lines, self.notes = list(lines), []

    async def reply(self, mia_said, note=""):
        self.notes.append(note)
        return self.lines.pop(0)


async def test_a_scripted_happy_path_is_scored_end_to_end(client, resolver):
    plan = build_plan(personas=["NG_C_NV"], paths=["SHP"])[0]
    case = plan.case
    route = json.dumps(
        {
            "origin_city": case.origin.city,
            "origin_state": case.origin.state,
            "destination_city": case.destination.city,
            "destination_state": case.destination.state,
        }
    )
    year, make, model = case.vehicles[0].split(" ", 2)
    car = json.dumps({"year": int(year), "make": make, "model": model})
    mia = ScriptedLLM(
        [
            Step(text="Where are you shipping from, and where to?"),
            Step(calls=[("save_origin_destination", route)]),
            Step(text="What's the year, make and model?"),
            Step(calls=[("save_vehicle", car)]),
            Step(text="Is that correct?"),
            Step(calls=[("get_quote", "{}")]),
            Step(text="Your estimated cost is $0. Anything else?"),
            Step(calls=[("end_call", "{}")]),
            Step(text="Thanks for calling. Goodbye!"),
        ]
    )
    caller = ScriptedCaller(
        [
            "Sure.",
            f"From {case.origin.label} to {case.destination.label}.",
            f"It's a {case.vehicles[0]}.",
            "Yes, that's right.",
            "No thanks, goodbye.",
        ]
    )
    services = Services(
        carhauler=client, resolver=resolver, geocode=fake_city_to_zip, transfer=lambda: None
    )
    record = await converse(plan, services, caller, mia_llm=mia)
    assert record["outcome"] == "ended"
    assert caller.notes[-1].startswith("Mia gave you the price")
    checks = record["checks"]
    assert checks["quoted"] and checks["route"] and checks["vehicles"] and checks["quote_matches"]
    assert not checks["price_spoken"]  # the script said $0, not the real price
    assert len(record["turns"]) == 5


def _record(path="SHP", **final):
    base = {
        "origin": "Miami, Florida",
        "destination": "Boston, Massachusetts",
        "vehicles": ["2020 Toyota Camry"],
        "quote_total": 1320,
        "quote_ids": ["Q1"],
        "vehicle_ids": ["Q1"],
        "end_reason": "mia",
        "transfer": None,
    }
    return {
        "id": f"NG_C_NV__{path}",
        "persona": "NG_C_NV",
        "path": path,
        "error": None,
        "outcome": "ended",
        "truth": {
            "origin": "Miami, Florida",
            "destination": "Boston, Massachusetts",
            "vehicles": ["2020 Toyota Camry"],
        },
        "final": {**base, **final},
        "turns": [
            {
                "n": 1,
                "mia": "Your estimated cost is $1,320.",
                "ms": 500,
                "caller": "",
                "note": "answer",
                "tools": [],
                "dropped": [],
            }
        ],
        "fragments": [],
        "planned_fragments": [],
        "dropped_calls": 0,
        "greeting": "Hi",
        "usage": {"mia_in": 1000, "mia_out": 10, "caller_in": 100, "caller_out": 10},
    }


def test_score_checks_the_ground_truth():
    assert all(score(_record()).values())
    wrong = score(_record(vehicles=["2010 Toyota Camry"]))
    assert not wrong["vehicles"] and wrong["route"]
    stale = score(_record(quote_ids=["Q1"], vehicle_ids=["Q2"]))  # changed, not re-quoted
    assert not stale["quote_matches"]
    rang = score(_record(transfer="pending"))
    assert not rang["no_transfer"]


def test_score_by_path_expectations():
    ap3 = score(_record("AP_three", quote_total=None, end_reason="off_topic"))
    assert ap3["no_quote"] and ap3["off_topic_end"] and "quoted" not in ap3
    person = score(_record("NHP_person", quote_total=None, transfer="pending"))
    assert person["transferred"]
    rec = _record("QHP")
    rec["planned_fragments"] = ["faq", "faq"]
    rec["fragments"] = [{"kind": "faq", "turn": 1, "text": "", "words": [["cost"]]}]
    checks = score(rec)
    assert checks["faq_answered"] and not checks["fragments_fired"]


def test_a_run_leaves_its_transcripts_and_an_index(tmp_path):
    rec = _record()
    rec["checks"] = score(rec)
    rec["passed"] = all(rec["checks"].values())
    meta = {
        "started": "2026-11-10T23:10:00+00:00",
        "minutes": 1.0,
        "label": "test",
        "mia_model": "openai/gpt-oss-20b",
        "caller_model": "openai/gpt-oss-120b",
        "commit": "abc1234",
    }
    folder = report.write_run(
        tmp_path / "runs", meta, [rec], {"faq_mid_call": {"runs": 3, "passed": 2}}
    )
    assert {f.name for f in folder.iterdir()} == {
        "report.md",
        "summary.json",
        "transcripts.jsonl",
        "transcripts.md",
    }
    assert json.loads((folder / "transcripts.jsonl").read_text(encoding="utf-8"))["id"] == rec["id"]
    md = (folder / "report.md").read_text(encoding="utf-8")
    assert "1/1 calls passed" in md and "`faq_mid_call` | 2/3" in md
    index = report.write_index(tmp_path / "runs").read_text(encoding="utf-8")
    assert f"runs/{folder.name}/report.md" in index and "`faq_mid_call` 2/3" in index


def test_errors_are_scrubbed_before_they_go_public():
    from evals.sim.run import rate_limited, scrub

    err = "429 Rate limit reached in organization `org_01kexample123` request_id=req_01mabc999"
    clean_err = scrub(err)
    assert "org_01kexample123" not in clean_err and "req_01mabc999" not in clean_err
    assert rate_limited({"error": clean_err}) and not rate_limited({"error": None})
