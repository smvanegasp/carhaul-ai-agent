"""Noisy calls: does Mia still answer in a classroom, on the subway, in a cafe? (mia/noise.py)

A scripted caller (mia/smoke.py) phones the running worker with background noise mixed into
its microphone for the whole call, also while Mia talks, which is when she gets cut off. Each
noise is played at each level against each noise-handling profile, and every call is scored:

    uv run python -m mia.main dev                       # terminal 1: a local worker
    uv run python -m evals.noisy_calls --label before   # terminal 2 (in agent/)

Noises (16 kHz, built once and cached in ``~/.cache/mia/noise/``):

- ``classroom``: six other people talking at once, near and far (Deepgram Aura voices that
  aren't Mia's or the caller's, reading ordinary chatter, a few lines with cities and cars in
  them, since those are what Mia could wrongly save).
- ``subway``: rumble, rail clacks and three people talking.
- ``cafe``: hiss, cups and five people talking.
- any ``.wav`` file: a real recording (e.g. a minute of the classroom on a phone).

Levels are the caller's voice over the noise in dB (``--snrs``): 12 is a lively room with the
phone at your mouth, 5 is loud.

Profiles (``--profiles``): ``baseline`` (no noise handling, how Mia was), ``filter`` (background
voice cancellation only), ``full`` (filter + turn limit + noisy-call mode).

Mia speaks with a Deepgram voice (``--voice``, default ``deepgram-thalia``): her voice doesn't
change what she hears, and Deepgram is the provider we pay for anyway (Sergio, 2026-11-12: no
Cartesia; its credits are spent). ``--resume <run folder>`` finishes a stopped run.

Cost: each call is about a minute of Deepgram, Groq and LiveKit, and at most one
CarHauler trim lookup (the script stops before the quote). The default grid is
3 noises x 2 levels x 3 profiles + 3 quiet calls = 21 calls, about 25 minutes.

Each run is saved to ``evals/noisy_calls/runs/<stamp>_<label>/`` (report + every call's
transcript and events) and listed in ``evals/noisy_calls/README.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

from mia import smoke

RATE = smoke.SAMPLE_RATE
VOICE = "deepgram-thalia"
CACHE = Path.home() / ".cache" / "mia" / "noise"
HERE = Path(__file__).resolve().parent / "noisy_calls"
TRACK_SECONDS = 60

LINES = [
    "Hi, I need to ship my car from Miami, Florida to Boston, Massachusetts.",
    "It's a 2020 Toyota Camry.",
    "I'm just checking prices for now. I'll call back later, bye!",
]

# Not Mia's Deepgram voices (Thalia, Athena) nor the caller's (Arcas).
BABBLE_VOICES = [
    "aura-2-andromeda-en",
    "aura-2-helena-en",
    "aura-2-apollo-en",
    "aura-2-luna-en",
    "aura-2-orion-en",
    "aura-2-hera-en",
]
CHATTER = [
    "Did you finish the reading for today's case?",
    "I think the professor said the exam is open book.",
    "Can you send me the slides from last week?",
    "We should meet at the library after class.",
    "I'm flying to Denver on Friday for the conference.",
    "My brother just bought a used Honda Accord.",
    "Honestly the second question was way harder than the first.",
    "Are you going to the networking event tonight?",
    "I left my charger in the other room again.",
    "The coffee downstairs is so much better than the one upstairs.",
    "She drove all the way from Chicago to Austin last summer.",
    "Wait, which group are you in for the project?",
    "I need to call my landlord about the heating.",
    "Let's split the presentation into three parts.",
    "Did anyone take notes on the pricing framework?",
    "I can't believe it's already November.",
]


# --- noise tracks ----------------------------------------------------------------------------


async def _clip(text: str, voice: str) -> np.ndarray:
    """One TTS line as float samples, cached on disk (Aura isn't free)."""
    name = re.sub(r"[^a-z0-9]+", "-", f"{voice}-{text}".lower()).strip("-")[:120]
    path = CACHE / "clips" / f"{name}.npy"
    if path.exists():
        return np.load(path)
    smoke.CALLER_VOICE, old = voice, smoke.CALLER_VOICE
    try:
        pcm = await smoke.synthesize(text)
    finally:
        smoke.CALLER_VOICE = old
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, samples)
    return samples


async def _talker(voice: str, rng: np.random.Generator) -> np.ndarray:
    """One person talking on and off for TRACK_SECONDS."""
    out = np.zeros(TRACK_SECONDS * RATE, dtype=np.float32)
    pos = int(rng.uniform(0, 3) * RATE)
    order = rng.permutation(len(CHATTER))
    i = 0
    while pos < len(out):
        clip = await _clip(CHATTER[order[i % len(order)]], voice)
        end = min(len(out), pos + len(clip))
        out[pos:end] += clip[: end - pos]
        pos = end + int(rng.uniform(0.3, 1.8) * RATE)
        i += 1
    return out


async def _babble(voices: int, rng: np.random.Generator) -> np.ndarray:
    """``voices`` people at different distances (one fairly near, the rest farther)."""
    tracks = [await _talker(v, rng) for v in BABBLE_VOICES[:voices]]
    gains = [1.0] + [float(g) for g in rng.uniform(0.35, 0.7, voices - 1)]
    return sum(g * _unit(t) for g, t in zip(gains, tracks, strict=True))


def _unit(x: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x**2))) or 1.0
    return (x / rms).astype(np.float32)


def _smooth(x: np.ndarray, width: int) -> np.ndarray:
    return np.convolve(x, np.ones(width) / width, mode="same")


async def build(name: str) -> np.ndarray:
    """The noise track ``name`` at RMS 1, cached."""
    path = CACHE / f"{name}.npy"
    if path.exists():
        return np.load(path)
    rng = np.random.default_rng(7)
    n = TRACK_SECONDS * RATE
    t = np.arange(n) / RATE
    if name == "classroom":
        track = _unit(await _babble(6, rng)) + 0.1 * _unit(rng.standard_normal(n))
    elif name == "subway":
        rumble = _unit(_smooth(rng.standard_normal(n), 60)) * (0.7 + 0.3 * np.sin(t * 1.9))
        clacks = np.zeros(n, dtype=np.float32)
        burst = rng.standard_normal(int(0.03 * RATE)) * np.exp(-np.linspace(0, 6, int(0.03 * RATE)))
        for start in np.arange(0.5, TRACK_SECONDS - 1, 1.15):
            for offset in (0.0, 0.13):
                i = int((start + offset) * RATE)
                clacks[i : i + len(burst)] += burst
        track = _unit(rumble) + 0.8 * _unit(clacks) + 0.6 * _unit(await _babble(3, rng))
    elif name == "cafe":
        hiss = _unit(_smooth(rng.standard_normal(n), 4))
        clinks = np.zeros(n, dtype=np.float32)
        ring = np.arange(int(0.08 * RATE)) / RATE
        for start in rng.uniform(0, TRACK_SECONDS - 1, 30):
            tone = np.sin(2 * np.pi * rng.uniform(2500, 4500) * ring) * np.exp(-ring * 60)
            i = int(start * RATE)
            clinks[i : i + len(tone)] += tone
        track = 0.3 * hiss + 0.5 * _unit(clinks) + _unit(await _babble(5, rng))
    else:
        raise ValueError(f"unknown noise {name!r}: classroom, subway, cafe or a .wav file")
    track = _unit(track)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(path, track)
    return track


def read_wav(path: str) -> np.ndarray:
    """A recording as mono float samples at 16 kHz, RMS 1."""
    with wave.open(path, "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path}: 16-bit PCM WAV only")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, channels).mean(axis=1)
    if rate != RATE:
        x = np.interp(np.arange(0, len(x), rate / RATE), np.arange(len(x)), x)
    return _unit(x.astype(np.float32))


async def speech_rms(lines: list[str]) -> float:
    """The caller's loudness while talking (samples above a floor, so pauses don't count)."""
    voice = np.concatenate([await _clip(line, smoke.CALLER_VOICE) for line in lines])
    active = voice[np.abs(voice) > 0.02 * np.abs(voice).max()]
    return float(np.sqrt(np.mean(active**2)))


async def scaled_noise(name: str, snr_db: float, lines: list[str]) -> np.ndarray:
    """The noise track at ``snr_db`` below the caller's voice."""
    track = read_wav(name) if name.lower().endswith(".wav") else await build(name)
    return track * (await speech_rms(lines) / 10 ** (snr_db / 20))


# --- scoring ---------------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def score(result: dict[str, Any]) -> dict[str, Any]:
    """What a caller would notice, from one call's result (smoke.run)."""
    events = result["events"]
    tools = [e for e in events if e.get("type") == "tool"]
    ok = {e["name"] for e in tools if e.get("ok")}
    said = [w for line in result["lines"] for w in _words(line)]
    heard = [w for h in result["heard"] if h["who"] == "caller" for w in _words(h["text"])]
    script = set(said)
    responses = result["responses"]
    timed = [r for r in responses if r is not None]
    return {
        "greeted": result["greeted"],
        "answered": sum(r is not None for r in responses),
        "lines": len(result["lines"]),
        "p50_s": round(statistics.median(timed), 1) if timed else None,
        "route": "save_origin_destination" in ok,
        "vehicle": "save_vehicle" in ok,
        "hung_up": result["hung_up"],
        "cut_off": sum(
            1
            for e in events
            if e.get("type") == "turn" and e.get("role") == "mia" and e.get("interrupted")
        ),
        "long_turns": sum(1 for e in tools if e["name"] == "end_long_turn"),
        "noisy_mode": any(e["name"] == "noisy_mode" for e in tools),
        # Of the caller's words, how many Mia's speech-to-text got; and how much of what it
        # heard from the caller was someone else (words not in the script).
        "recall": round(len(script & set(heard)) / len(script), 2) if script else None,
        "extra_words": sum(1 for w in heard if w not in script),
    }


# --- the run ---------------------------------------------------------------------------------


@dataclass
class Case:
    noise: str | None
    snr: float | None
    profile: str

    @property
    def key(self) -> str:
        where = "quiet" if self.noise is None else f"{Path(self.noise).stem}@{self.snr:g}dB"
        return f"{where}/{self.profile}"


def grid(noises: list[str], snrs: list[float], profiles: list[str], quiet: bool) -> list[Case]:
    cases = [Case(None, None, p) for p in profiles] if quiet else []
    cases += [Case(n, s, p) for n in noises for s in snrs for p in profiles]
    return cases


def _row(case: Case, s: dict[str, Any]) -> str:
    yes = {True: "yes", False: "**no**"}
    p50 = f"{s['p50_s']} s" if s["p50_s"] is not None else "-"
    answered = f"{s['answered']}/{s['lines']}"
    if s["answered"] < s["lines"]:
        answered = f"**{answered}**"
    where = "quiet" if case.noise is None else Path(case.noise).stem
    level = "-" if case.snr is None else f"{case.snr:g} dB"
    return (
        f"| {where} | {level} | {case.profile} | {answered} | {p50} | {yes[s['route']]} | "
        f"{yes[s['vehicle']]} | {s['cut_off']} | {s['long_turns']} | "
        f"{'yes' if s['noisy_mode'] else '-'} | {s['recall']} | {s['extra_words']} | "
        f"{yes[s['hung_up']]} |"
    )


HEADER = (
    "| Noise | Caller over noise | Profile | Lines answered | Response p50 | Route saved | "
    "Car saved | Mia cut off | Long turns ended | Noisy mode | Caller words heard | "
    "Other words heard | Ended cleanly |\n"
    "| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- | ---: | ---: | --- |"
)


def summary(calls: list[dict[str, Any]]) -> str:
    """Per profile: share of lines answered and of calls that saved both details."""
    out = ["| Profile | Noisy calls | Lines answered | Route + car saved | Mia cut off (total) |"]
    out.append("| --- | ---: | ---: | ---: | ---: |")
    profiles = sorted({c["case"]["profile"] for c in calls}, key=list(PROFILE_ORDER).index)
    for profile in profiles:
        noisy = [c for c in calls if c["case"]["profile"] == profile and c["case"]["noise"]]
        if not noisy:
            continue
        lines = sum(c["score"]["lines"] for c in noisy)
        answered = sum(c["score"]["answered"] for c in noisy)
        both = sum(c["score"]["route"] and c["score"]["vehicle"] for c in noisy)
        cut = sum(c["score"]["cut_off"] for c in noisy)
        out.append(
            f"| {profile} | {len(noisy)} | {answered}/{lines} ({answered / lines:.0%}) | "
            f"{both}/{len(noisy)} | {cut} |"
        )
    return "\n".join(out)


PROFILE_ORDER = ("baseline", "filter", "full")


def write_report(folder: Path, label: str, started: str, calls: list[dict[str, Any]]) -> str:
    rows = "\n".join(_row(Case(**c["case"]), c["score"]) for c in calls)
    report = f"""# Noisy calls: {label}

Run {started}. Script: {" / ".join(f'"{line}"' for line in LINES)}
How it works: [`agent/evals/noisy_calls.py`](../../../noisy_calls.py).

## By profile

{summary(calls)}

## Every call

{HEADER}
{rows}

"Caller words heard": share of the script's words Mia's speech-to-text got from the caller.
"Other words heard": words it attributed to the caller that weren't in the script (other
people's speech getting through). Transcripts and events: `calls.json`.
"""
    (folder / "report.md").write_text(report, encoding="utf-8")
    return report


def add_to_index(folder: Path, label: str, started: str, calls: list[dict[str, Any]]) -> None:
    index = HERE / "README.md"
    text = index.read_text(encoding="utf-8")
    noisy = [c for c in calls if c["case"]["noise"]]
    by = {}
    for p in PROFILE_ORDER:
        mine = [c for c in noisy if c["case"]["profile"] == p]
        if mine:
            lines = sum(c["score"]["lines"] for c in mine)
            answered = sum(c["score"]["answered"] for c in mine)
            by[p] = f"{answered}/{lines}"
    answered = ", ".join(f"{p} {v}" for p, v in by.items())
    row = (
        f"| {started} | {label} | {len(calls)} | {answered} | "
        f"[report](runs/{folder.name}/report.md) |"
    )
    marker = "| --- | --- | ---: | --- | --- |\n"
    text = text.replace(marker, marker + row + "\n", 1)
    index.write_text(text, encoding="utf-8")


async def main(args: argparse.Namespace) -> None:
    cases = grid(args.noises, args.snrs, args.profiles, not args.no_quiet)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    calls: list[dict[str, Any]] = []
    if args.resume:
        folder = Path(args.resume)
        args.label = folder.name.split("_", 1)[1]
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))
        done = {Case(**c["case"]).key for c in calls}
        cases = [c for c in cases if c.key not in done]
        print(f"resuming {folder.name}: {len(done)} done, {len(cases)} to go")
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
        folder = (Path(args.out) if args.out else HERE / "runs") / f"{stamp}_{args.label}"
        folder.mkdir(parents=True, exist_ok=True)
    for i, case in enumerate(cases, 1):
        track = await scaled_noise(case.noise, case.snr, LINES) if case.noise else None
        print(f"[{i}/{len(cases)}] {case.key}", flush=True)
        try:
            result = await smoke.run(
                LINES,
                voice=args.voice,
                wait=20,
                noise=track,
                profile=case.profile,
                quiet=not args.verbose,
            )
        except Exception as err:  # one broken call shouldn't lose the run
            print(f"    failed: {err!r}")
            continue
        s = score(result)
        print(
            f"    answered {s['answered']}/{s['lines']}, route {s['route']}, car "
            f"{s['vehicle']}, cut off {s['cut_off']}, long turns {s['long_turns']}, "
            f"noisy {s['noisy_mode']}, recall {s['recall']}, extra {s['extra_words']}",
            flush=True,
        )
        calls.append({"case": vars(case), "score": s, "result": result})
        (folder / "calls.json").write_text(json.dumps(calls, indent=1), encoding="utf-8")
        await asyncio.sleep(3)  # let the worker close the room
    print("\n" + write_report(folder, args.label, started, calls))
    if not args.out and folder.name not in (HERE / "README.md").read_text(encoding="utf-8"):
        add_to_index(folder, args.label, started, calls)
    print(f"saved to {folder}")


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--label", default="run")
    parser.add_argument("--noises", nargs="+", default=["classroom", "subway", "cafe"])
    parser.add_argument("--snrs", nargs="+", type=float, default=[12, 5])
    parser.add_argument("--profiles", nargs="+", default=list(PROFILE_ORDER))
    parser.add_argument("--no-quiet", action="store_true", help="skip the quiet control calls")
    parser.add_argument("--out", help="a scratch folder (not indexed)")
    parser.add_argument("--verbose", action="store_true", help="print each call's transcript")
    parser.add_argument("--voice", default=VOICE, help="Mia's voice (mia/voices.py); Deepgram")
    parser.add_argument("--resume", help="a run folder to finish (skips the calls it has)")
    asyncio.run(main(parser.parse_args()))
