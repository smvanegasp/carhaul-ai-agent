"""The files each simulation run leaves, all public in the repo:

    evals/simulations/README.md               every run so far, newest first
    evals/simulations/runs/<run>/report.md    pass rates by path and persona, failures
    evals/simulations/runs/<run>/transcripts.md     every call, readable
    evals/simulations/runs/<run>/transcripts.jsonl  every call, full record (one per line)
    evals/simulations/runs/<run>/summary.json       the numbers behind the report

The transcripts come from fake APIs and a simulated caller: no real person, phone number or key
is in them.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from evals.sim.catalog import PATHS, PERSONAS

# Groq list prices, USD per 1M tokens (input, output), checked 2026-11. An estimate: cached
# input is cheaper, so the real bill is at most this.
PRICES = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
}


def _cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    if model not in PRICES:
        return None
    p_in, p_out = PRICES[model]
    return (tokens_in * p_in + tokens_out * p_out) / 1e6


def _group(records: list[dict]) -> dict[str, Any]:
    n = len(records)
    turns = [len(r["turns"]) for r in records]
    ms = [t["ms"] for r in records for t in r["turns"]]
    return {
        "n": n,
        "passed": sum(r["passed"] for r in records),
        "quoted": sum(r["final"]["quote_total"] is not None for r in records),
        "avg_turns": round(statistics.mean(turns), 1) if turns else 0,
        "dropped_per_call": round(sum(r["dropped_calls"] for r in records) / n, 2) if n else 0,
        "p50_ms": round(statistics.median(ms)) if ms else None,
    }


def summarize(meta: dict, records: list[dict], scenarios: dict | None = None) -> dict:
    usage = Counter()
    for r in records:
        usage.update({k: v for k, v in r.get("usage", {}).items() if isinstance(v, int)})
    mia_cost = _cost(meta["mia_model"], usage["mia_in"], usage["mia_out"])
    caller_cost = _cost(meta["caller_model"], usage["caller_in"], usage["caller_out"])
    failed_checks = Counter(k for r in records for k, ok in r["checks"].items() if not ok)
    n = len(records)
    return {
        **meta,
        "n": n,
        "passed": sum(r["passed"] for r in records),
        "pass_rate": sum(r["passed"] for r in records) / n if n else 0.0,
        "errors": sum(r["error"] is not None for r in records),
        "outcomes": dict(Counter(r["outcome"] for r in records)),
        "by_path": {
            p.code: _group([r for r in records if r["path"] == p.code])
            for p in PATHS
            if any(r["path"] == p.code for r in records)
        },
        "by_persona": {
            p.code: _group([r for r in records if r["persona"] == p.code])
            for p in PERSONAS
            if any(r["persona"] == p.code for r in records)
        },
        "failed_checks": dict(failed_checks.most_common()),
        "usage": dict(usage),
        "cost_usd": round((mia_cost or 0) + (caller_cost or 0), 4)
        if mia_cost is not None or caller_cost is not None
        else None,
        "scenarios": scenarios or {},
    }


def _pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "-"


def _table(title: str, groups: dict[str, dict], about: dict[str, str] | None = None) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| | Calls | Passed | Quoted | Turns (avg) | Dropped calls / call | Mia p50 (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, g in groups.items():
        name = f"`{key}`" + (f" {about[key]}" if about and key in about else "")
        lines.append(
            f"| {name} | {g['n']} | {_pct(g['passed'], g['n'])} | {_pct(g['quoted'], g['n'])} "
            f"| {g['avg_turns']} | {g['dropped_per_call']} | {g['p50_ms'] or '-'} |"
        )
    return [*lines, ""]


def report_md(summary: dict, records: list[dict]) -> str:
    s = summary
    cost = f"${s['cost_usd']:.2f}" if s["cost_usd"] is not None else "n/a"
    lines = [
        f"# Simulation run {s['started']} ({s['label']})",
        "",
        f"**{s['passed']}/{s['n']} calls passed ({s['pass_rate']:.0%})**. Mia: "
        f"`{s['mia_model']}`, caller: `{s['caller_model']}`, commit `{s['commit'] or '?'}`, "
        f"{s['minutes']} min, about {cost} in Groq tokens. API errors: {s['errors']}.",
        "",
        "Fake CarHauler and geocoder; a model plays the caller. Every call is scored in code "
        "against its ground truth (`evals/sim/run.py`, `score`). Transcripts: "
        "[transcripts.md](transcripts.md).",
        "",
        "Outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(s["outcomes"].items())),
        "",
    ]
    lines += _table("By path", s["by_path"], {p.code: p.about for p in PATHS})
    lines += _table("By persona", s["by_persona"])

    personas = list(s["by_persona"])
    paths = list(s["by_path"])
    grid = {(r["persona"], r["path"]): [] for r in records}
    for r in records:
        grid[(r["persona"], r["path"])].append(r["passed"])
    lines += [
        "## Persona x path",
        "",
        "| | " + " | ".join(f"`{p}`" for p in paths) + " |",
        "| --- |" + " :---: |" * len(paths),
    ]
    for persona in personas:
        cells = []
        for p in paths:
            got = grid.get((persona, p))
            cells.append(
                ""
                if not got
                else f"{sum(got)}/{len(got)}"
                if len(got) > 1
                else ("pass" if got[0] else "**FAIL**")
            )
        lines.append(f"| `{persona}` | " + " | ".join(cells) + " |")
    lines.append("")

    if s["failed_checks"]:
        lines += ["## Failed checks", "", "| Check | Calls |", "| --- | ---: |"]
        lines += [f"| `{k}` | {v} |" for k, v in s["failed_checks"].items()]
        lines.append("")

    if s["scenarios"]:
        lines += [
            "## Scenario suite (tests/test_scenarios.py)",
            "",
            "| Scenario | Passed |",
            "| --- | ---: |",
        ]
        for sid, r in sorted(
            s["scenarios"].items(), key=lambda kv: kv[1]["passed"] / kv[1]["runs"]
        ):
            lines.append(f"| `{sid}` | {r['passed']}/{r['runs']} |")
        lines.append("")

    failures = [r for r in records if not r["passed"]]
    if failures:
        lines += ["## Failures", ""]
        for r in failures:
            bad = ", ".join(f"`{k}`" for k, ok in r["checks"].items() if not ok)
            note = f" ({r['error']})" if r["error"] else ""
            lines.append(
                f"- [{r['id']}](transcripts.md#{r['id'].lower()}): {r['outcome']}, "
                f"failed {bad}{note}"
            )
        lines.append("")
    return "\n".join(lines)


def _tool_line(t: dict) -> str:
    return f"`{t['name']}({t['args']})`" + ("" if t["ok"] else " (refused)")


def transcripts_md(meta: dict, records: list[dict]) -> str:
    lines = [
        f"# Transcripts, run {meta['started']} ({meta['label']})",
        "",
        "The caller is a model playing a persona; `[note]` is what the test told it to do "
        "that turn. Tool calls Mia made are in code style; dropped ones were stopped by "
        "the guardrail before they ran.",
        "",
    ]
    for r in records:
        mark = "pass" if r["passed"] else "FAIL"
        truth = r["truth"]
        lines += [
            f'<a id="{r["id"].lower()}"></a>',
            f"## {r['id']}: {mark}",
            "",
            f"Persona `{r['persona']}`, path `{r['path']}`. Truth: {truth['origin']} to "
            f"{truth['destination']}, {', '.join(truth['vehicles'])}. Outcome: "
            f"**{r['outcome']}**"
            + (f", quote ${r['final']['quote_total']:,}" if r["final"]["quote_total"] else ""),
        ]
        bad = [k for k, ok in r["checks"].items() if not ok]
        if bad:
            lines.append(f"Failed: {', '.join(bad)}")
        if r["error"]:
            lines.append(f"Error: `{r['error']}`")
        lines += ["", f"- **Mia:** {r['greeting']}"]
        for t in r["turns"]:
            note = "" if t["note"] == "answer" else f" `[{t['note']}]`"
            lines.append(f"- **Caller**{note}: {t['caller']}")
            for d in t["dropped"]:
                lines.append(f"  - dropped `{d['tool']}({d['args']})`: {d['why']}")
            for tool in t["tools"]:
                lines.append(f"  - {_tool_line(tool)}")
            lines.append(f"- **Mia** ({t['ms']} ms): {t['mia']}")
        lines.append("")
    return "\n".join(lines)


def _run_name(meta: dict) -> str:
    stamp = meta["started"].replace(":", "").replace("-", "")[:13]  # 20261110T2310
    return f"{stamp}Z_{meta['label']}"


def write_run(out: Path, meta: dict, records: list[dict], scenarios: dict | None = None) -> Path:
    folder = out / _run_name(meta)
    folder.mkdir(parents=True, exist_ok=True)
    summary = summarize(meta, records, scenarios)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (folder / "transcripts.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (folder / "transcripts.md").write_text(
        transcripts_md(meta, records), encoding="utf-8", newline="\n"
    )
    (folder / "report.md").write_text(report_md(summary, records), encoding="utf-8", newline="\n")
    return folder


INDEX_HEAD = """# Simulation runs

AI-vs-AI simulations of Mia (stage 7): a model plays one of 8 caller personas through one of 9
paths (happy, questions, changes, a person, off-topic), against fake CarHauler and geocoding
APIs, and code scores every call against its ground truth. A nightly GitHub workflow
(`.github/workflows/simulations.yml`) adds a run here; `uv run python -m evals.sim.run` (in
`agent/`) runs one locally. How it works: [`agent/evals/sim/`](../sim/).

Every run keeps its full transcripts. Newest first:

| Run (UTC) | Label | Mia | Caller | Calls | Passed | Weakest scenario | Cost | |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | --- |
"""


def write_index(out: Path) -> Path:
    rows = []
    for summary_file in sorted(out.glob("*/summary.json"), reverse=True):
        s = json.loads(summary_file.read_text(encoding="utf-8"))
        weakest = "-"
        if s.get("scenarios"):
            sid, r = min(s["scenarios"].items(), key=lambda kv: kv[1]["passed"] / kv[1]["runs"])
            weakest = f"`{sid}` {r['passed']}/{r['runs']}"
        cost = f"${s['cost_usd']:.2f}" if s.get("cost_usd") is not None else "-"
        name = summary_file.parent.name
        rows.append(
            f"| {s['started']} | {s['label']} | `{s['mia_model']}` | `{s['caller_model']}` | "
            f"{s['n']} | {s['passed']} ({s['pass_rate']:.0%}) | {weakest} | {cost} | "
            f"[report](runs/{name}/report.md) |"
        )
    index = out.parent / "README.md"
    index.write_text(INDEX_HEAD + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return index
