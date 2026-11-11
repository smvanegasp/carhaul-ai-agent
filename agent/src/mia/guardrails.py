"""Output guardrail: check the model's tool calls before they run.

``Mia.llm_node`` passes every tool call the model emits through ``check_call``. A call that
would save details the caller never said, or quote before the caller confirmed, is dropped
from the model's output, so it never runs and never triggers another model step. That matters
in voice: with gpt-oss-20b, each refused call used to make Mia ask the same question again
("What's the third car? What's the third car?"), and enough of them hit the tool-step limit
and crashed the turn.

If dropping leaves Mia with nothing to say, ``fallback_line`` gives a deterministic line built
from the call state (the next question, or the read-back to confirm).

The tools keep their own grounding checks too (defense in depth, and unit-tested there).
"""

from __future__ import annotations

import json
import re
from typing import Any

from mia import grounding
from mia.state import QuoteSession

ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def check_call(
    name: str,
    arguments: str,
    state: QuoteSession,
    said: str,
    last_said: str,
    mia_last: str = "",
) -> str | None:
    """Why this call must not run, or None if it may."""
    try:
        args: dict[str, Any] = json.loads(arguments or "{}") or {}
    except ValueError:
        return None  # let the tool layer report malformed arguments
    if name == "save_origin_destination":
        cities = [args.get("origin_city"), args.get("destination_city")]
        if not any(c and grounding.city_said(c, said) for c in cities):
            return "no city the caller said"
    elif name == "save_vehicle":
        checks = [
            (args.get("year"), grounding.year_said),
            (args.get("make"), grounding.make_said),
            (args.get("model"), grounding.model_said),
            (args.get("vehicle_type"), grounding.vehicle_type_said),
        ]
        if not any(value and said_fn(value, said) for value, said_fn in checks):
            return "no vehicle detail the caller said"
        if _already_saved_this_turn(args, state, last_said):
            return "same vehicle already saved this turn"
    elif name == "get_quote":
        # With details missing the tool itself answers MISSING_INFO, which gives the model a
        # step to save what the caller just said (it sometimes skips save_vehicle).
        if not state.missing and not grounding.is_confirmation(last_said):
            return "caller has not confirmed"
    elif name == "update_vehicle":
        checks = [
            (args.get("year"), grounding.year_said),
            (args.get("make"), grounding.make_said),
            (args.get("model"), grounding.model_said),
            (args.get("vehicle_type"), grounding.vehicle_type_said),
        ]
        changed = any(value and said_fn(value, said) for value, said_fn in checks)
        if not changed and args.get("drivable") is None:
            return "no vehicle detail the caller said"
    elif name == "remove_vehicle":
        if not grounding.wants_removal(last_said):
            return "caller did not ask to remove a vehicle"
    elif name == "undo_last_change":
        if not grounding.wants_undo(last_said):
            return "caller did not ask to undo a change"
    elif name == "note_off_topic":
        # The third one ends the call: never on a turn about shipping, a city, a vehicle or a yes.
        if (
            not last_said.strip()
            or grounding.is_on_topic(last_said)
            or grounding.is_short_yes(last_said)
            or grounding.vehicle_count_said(last_said)
        ):
            return "caller's message is about the quote"
    elif name == "request_human":
        # It rings a real phone (stage 9): only on the caller's own request, or a yes to Mia's
        # offer, never on a call the model made up.
        offered = grounding.offered_person(mia_last) and grounding.is_confirmation(last_said)
        if not (grounding.wants_person(last_said) or offered):
            return "caller did not ask for a person"
    return None


def _already_saved_this_turn(args: dict[str, Any], state: QuoteSession, last_said: str) -> bool:
    """The model sometimes saves the caller's one car again on its next step ("2025 Civic" x3).
    A repeat is allowed only if the caller's message mentions several ("two 2020 Corollas")."""
    same = [
        v
        for v in state.vehicles
        if v.saved_turn == state.caller_turns
        and (v.make or "").lower() == str(args.get("make") or "").lower()
        and (v.model or "").lower() == str(args.get("model") or "").lower()
        and args.get("year") in (None, v.year)
    ]
    if not same:
        return False
    return not re.search(r"\b(both|two|three|four|five|2|3|4|5)\b", last_said.lower())


def read_back(state: QuoteSession) -> str:
    """'Just to confirm, your 2025 Honda Civic will ship from Boston, Massachusetts to San
    Francisco, California. Is that correct?'"""
    labels = [v.label for v in state.vehicles]
    vehicles = f"your {_join(labels)}" if labels else "your vehicle"
    origin = state.origin.spoken if state.origin else "the pickup city"
    destination = state.destination.spoken if state.destination else "the delivery city"
    return f"Just to confirm, {vehicles} will ship from {origin} to {destination}. Is that correct?"


def fallback_line(state: QuoteSession) -> str:
    """What Mia says when the model only produced dropped tool calls."""
    if not state.origin and not state.destination:
        return "Where are you shipping the car from, and where is it going?"
    if not state.origin:
        return "And where will we pick it up?"
    if not state.destination:
        return "And where is it going?"
    expected = state.expected_vehicles or 1
    have = len(state.vehicles)
    if have < expected and state.partial_vehicle:
        return state.partial_question()
    if have < expected:
        if expected == 1:
            return "What's the year, make and model of the car?"
        nth = ORDINALS[have] if have < len(ORDINALS) else f"number {have + 1}"
        return f"What's the year, make and model of the {nth} car?"
    return read_back(state)


_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s+|(?=[A-Z‘“\"']))")


def tidy_speech(text: str) -> str:
    """Clean one step of the model's speech before it's spoken.

    gpt-oss-20b sometimes says its line twice in one go ("What's the second car?What's the
    second car?") or tacks on the next question ("...second car?What's the third car?"). Drop
    repeated sentences and stop after the first question: one question at a time.
    """
    out: list[str] = []
    seen: set[str] = set()
    for sentence in _SENTENCE_END.split(text.strip()):
        sentence = sentence.strip()
        key = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(sentence)
        if sentence.endswith("?"):
            break
    return " ".join(out)


# Mia's own closing line. On Sergio's call (2026-11-09) the caller said "Nope" to the Sergio
# offer and Mia answered "...Otherwise, have a great day!" without calling end_call, so the
# caller had to hang up. A closing line now ends the call once it has been spoken.
_GOODBYE = re.compile(
    r"\b(?:good ?bye|bye now|have an? (?:great|good|nice|wonderful|lovely) "
    r"(?:day|one|night|evening|afternoon|weekend)|take care|thanks? (?:you )?for calling)\b",
    re.IGNORECASE,
)


def is_goodbye(speech: str) -> bool:
    """True if Mia is closing the call (a goodbye in her last sentence)."""
    sentences = [s for s in _SENTENCE_END.split(speech.strip()) if s.strip()]
    return bool(sentences) and bool(_GOODBYE.search(sentences[-1]))


# Stage 7 simulation, 2026-11-10: the caller said "2022 Toyota RAV4 and 2017 Honda Civic",
# the model saved only the RAV4, then read back both cars; the caller said yes and got a
# one-car price. So a read-back Mia speaks is rebuilt from what's on file.
_READ_BACK = re.compile(
    r"\bship\w*\b.*\b(?:is that (?:all )?(?:correct|right)|does that sound right|"
    r"is this correct|correct\?|right\?)",
    re.IGNORECASE | re.DOTALL,
)


def honest_read_back(spoken: str, state: QuoteSession) -> str:
    """If Mia is reading the details back, say what's actually on file: the code's read-back
    when everything is there, otherwise the question for what's missing."""
    if not spoken or not _READ_BACK.search(spoken) or not (state.origin or state.vehicles):
        return spoken
    # Keep what comes before the read-back ("I've removed the Toyota."): only the read-back
    # itself is replaced (scenario remove_vehicle_after_quote failed 3/3 when all of it was).
    sentences = [x.strip() for x in _SENTENCE_END.split(spoken.strip()) if x.strip()]
    start = next(
        (
            i
            for i in range(len(sentences))
            if _READ_BACK.search(" ".join(sentences[i:]))
            and not _READ_BACK.search(" ".join(sentences[i + 1 :]))
        ),
        0,
    )
    while start > 0 and re.search(r"\bship", sentences[start - 1], re.IGNORECASE):
        start -= 1
    return " ".join([*sentences[:start], fallback_line(state)])


_ASKS_MODEL = re.compile(r"\bmodel\b[^.!?]*\?", re.IGNORECASE)


def no_model_again(spoken: str, state: QuoteSession) -> str:
    """Once the caller said they don't know the model, Mia asks for the body type instead of
    the model again."""
    if state.partial_vehicle.get("model_unknown") and spoken and _ASKS_MODEL.search(spoken):
        return state.partial_question()
    return spoken


def keep_going(spoken: str, state: QuoteSession) -> str:
    """After answering a question, Mia goes back to what's missing (CONVERSATION_DESIGN.md,
    per-turn logic). gpt-oss often stops after the answer ("We only quote open car shipping.")
    and the caller is left waiting (stage 8 FAQ scenario, 2026-11-10): a line with no question
    while details are missing gets the next question. Never on a goodbye, during a transfer, or
    once the call is ending.

    With everything on file but no quote yet, the next step is the read-back. Live call,
    2026-11-10: the caller asked about enclosed shipping right after the read-back, Mia
    answered without asking again, the caller waited, and silence ended the call before the
    quote. Not after an escalation (a failed lookup: Mia is offering a person instead)."""
    if not state.missing and (state.quote or state.escalated):
        return spoken
    if (
        not spoken
        or "?" in spoken
        or state.ended
        or state.hang_up_after_speech
        or state.transfer in ("pending", "connected")
        or is_goodbye(spoken)
    ):
        return spoken
    return f"{spoken} {fallback_line(state)}"
