"""What Mia's tools do, independent of LiveKit (so it's easy to test and to reuse).

Every function takes the call's ``QuoteSession`` plus the shared ``Services`` and returns a
small JSON-able dict:

    {"ok": True,  ..., "on_file": {...}, "next": "<what Mia should do now>"}
    {"ok": False, "error_code": "...", ..., "on_file": {...}, "next": "<how to recover>"}

``next`` is the per-tool error design from docs/CONVERSATION_DESIGN.md: for each result, and
especially each error, the tool tells the model what to say or ask. ``agent.py`` exposes these as
LLM function tools.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mia import grounding, phrases, transfer
from mia.carhauler import CarHaulerClient, CarHaulerError, ErrorCode
from mia.events import CallEvents
from mia.geo import CityToZipError, canonicalize_state, city_to_zip
from mia.pricing import QuoteRequest, quote_vehicles, summarize
from mia.state import Place, QuoteSession, Stage
from mia.vehicles import (
    VehicleError,
    VehicleErrorCode,
    VehicleResolver,
    normalize,
    normalize_vehicle_type,
    normalize_year,
)

Result = dict[str, Any]

NOT_SAID = (
    "The caller hasn't said that yet: don't assume details. Ask the caller for it in their own "
    "words."
)

ESCALATE = (
    "Apologize briefly: our system is having trouble right now. Offer to connect them with a "
    "licensed representative; if they agree, call request_human."
)


# The same detail failed three times in a row (a city or vehicle we can't find): stop asking.
STILL_NOT_FOUND = (
    "Apologize: you still can't find it in our system. Offer to connect them with a licensed "
    "representative who can help; if they agree, call request_human."
)
MAX_FAILURES = 3

OFF_TOPIC_LIMIT = 3


@dataclass
class Services:
    """What the tools use besides the call state (one per call)."""

    carhauler: CarHaulerClient
    resolver: VehicleResolver
    geocode: Callable[..., dict[str, Any]] = city_to_zip  # sync; run in a thread
    # Voice only: say the filler line and play the "calculating" sound while the quote is
    # computed (returns an awaitable that's done when Mia may read the price); hang up
    # (agent.py calls it once the goodbye has been spoken).
    before_quote: Callable[[str], Any] | None = None
    end_call: Callable[[], Any] | None = None
    # Voice with a trunk configured (transfer.py): ring the representative into the call.
    # agent.py starts it once Mia's "connecting you" line has been spoken.
    transfer: Callable[[], Any] | None = None
    # The call's events (live panel, call record). Text chat and tests get one that only
    # keeps them; the worker's also publishes them to the room.
    events: CallEvents = field(default_factory=CallEvents)
    extra: dict[str, Any] = field(default_factory=dict)


def _note_vehicle_count(state: QuoteSession, said: str | None) -> None:
    """The caller said how many vehicles ("2 cars"): remember it so Mia asks for each one."""
    if said:
        count = grounding.vehicle_count_said(said)
        if count:
            state.expected_vehicles = count


def _failed(state: QuoteSession, detail: str, code: str, hint: str, **data: Any) -> Result:
    """A detail the caller gave couldn't be found: ask again, or after the third time in a row,
    offer a person instead of asking forever."""
    state.failures[detail] = state.failures.get(detail, 0) + 1
    if state.failures[detail] >= MAX_FAILURES:
        return _err(state, code, STILL_NOT_FOUND, attempts=state.failures[detail], **data)
    return _err(state, code, hint, attempts=state.failures[detail], **data)


def _ok(state: QuoteSession, next_step: str, **data: Any) -> Result:
    return {"ok": True, **data, "on_file": state.snapshot(), "next": next_step}


def _err(state: QuoteSession, code: str, next_step: str, **data: Any) -> Result:
    if next_step in (ESCALATE, STILL_NOT_FOUND):
        state.escalated = True  # a transfer after this is a "forced" one
    return {"ok": False, "error_code": code, **data, "on_file": state.snapshot(), "next": next_step}


def _next_question(state: QuoteSession) -> str:
    missing = state.missing
    if not missing:
        return (
            "Everything is on file. Read it back in one sentence (each vehicle, origin city and "
            "state, destination city and state) and ask if it's correct. Call get_quote only "
            "after they confirm."
        )
    for side, word in (("origin", "from"), ("destination", "to")):
        st = state.states_without_city.get(side)
        if side in missing and st:
            return (
                f"They said {st} but no city: ask which city in {st} they're shipping {word} "
                f'(e.g. "Which city in {st}?").'
            )
    if "origin" in missing or "destination" in missing:
        which = " and ".join(m for m in missing if m in ("origin", "destination"))
        return f"Ask for the {which} (city and state)."
    if state.partial_vehicle and any(m.startswith("vehicle") for m in missing):
        return (
            f"They already said it's a {state.partial_label()}: don't ask for that again. Ask "
            f'only for what\'s missing, e.g. "{state.partial_question()}"'
        )
    if "vehicle" in missing:
        if state.expected_vehicles and state.expected_vehicles > 1:
            return (
                f"Ask for the year, make and model of the first of the {state.expected_vehicles} "
                "vehicles."
            )
        return "Ask for the year, make and model of the vehicle."
    nth, total = missing[0].removeprefix("vehicle ").split(" of ")
    return (
        f"Don't confirm yet: they're shipping {total} vehicles and you have {int(nth) - 1}. Ask "
        f"for the year, make and model of vehicle {nth}."
    )


# --- route -------------------------------------------------------------------------------

_GEO_HINTS = {
    "EMPTY_CITY": "Ask for the city name.",
    "STATE_UNRECOGNIZED": "You didn't catch the state for {city}. Ask which state it's in.",
    "CITY_NOT_FOUND": (
        "Say you couldn't find {city} in our system and ask if you got it right; ask them to "
        "repeat the city and its state."
    ),
    "ZERO_RESULTS": ("Say you couldn't find {city} and ask them to repeat the city and its state."),
    "STATE_MISMATCH": (
        "Say you couldn't find {city} in {state}. Ask them to confirm the city and the state."
    ),
    "NO_POSTAL_CODE": (
        "Say you couldn't pin down {city}. Ask for a nearby larger city in the same state."
    ),
}


# Nicknames the geocoder doesn't know (Sergio's call, 2026-11-11: "From LA to New York" ->
# "I couldn't find LA").
CITY_NICKNAMES = {
    "la": ("Los Angeles", "CA"),
    "l a": ("Los Angeles", "CA"),
    "nyc": ("New York", "NY"),
    "sf": ("San Francisco", "CA"),
    "san fran": ("San Francisco", "CA"),
    "philly": ("Philadelphia", "PA"),
    "vegas": ("Las Vegas", "NV"),
    "dc": ("Washington", "DC"),
    "d c": ("Washington", "DC"),
    "nola": ("New Orleans", "LA"),
    "atl": ("Atlanta", "GA"),
    "chi town": ("Chicago", "IL"),
    "the bay": ("San Francisco", "CA"),
}


async def _geocode(services: Services, city: str, state: str | None) -> Place:
    key = " ".join(re.findall(r"[a-z]+", city.lower()))
    if key in CITY_NICKNAMES:
        city, nick_state = CITY_NICKNAMES[key]
        state = state if state and key not in ("la", "l a") else nick_state
    r = await asyncio.to_thread(services.geocode, city, state)
    return Place(city=r["city"], state=r["state"], state_name=r["state_name"], zip=r["zip"])


async def save_origin_destination(
    state: QuoteSession,
    services: Services,
    *,
    origin_city: str | None = None,
    origin_state: str | None = None,
    destination_city: str | None = None,
    destination_state: str | None = None,
    said: str | None = None,
) -> Result:
    """``said``: everything the caller said so far, for the grounding check (None skips it)."""
    _note_vehicle_count(state, said)
    # A state with no city ("from Miami to California"): ask which city in it, on that side.
    for side, city, st in (
        ("origin", origin_city, origin_state),
        ("destination", destination_city, destination_state),
    ):
        if st and not city and (said is None or grounding.state_said(st, said)):
            state.states_without_city[side] = st
    if not origin_city and not destination_city:
        return _err(state, "NOTHING_TO_SAVE", _next_question(state))

    # Grounding guardrail: only cities the caller said; a state they didn't say is dropped
    # (the geocoder picks the best match and Mia confirms the state out loud).
    ignored: list[str] = []
    if said is not None:
        if origin_state and not grounding.state_said(origin_state, said):
            origin_state = None
        if destination_state and not grounding.state_said(destination_state, said):
            destination_state = None
        if origin_city and not grounding.city_said(origin_city, said):
            ignored.append(f"origin {origin_city}")
            origin_city = origin_state = None
        if destination_city and not grounding.city_said(destination_city, said):
            ignored.append(f"destination {destination_city}")
            destination_city = destination_state = None
        if not origin_city and not destination_city:
            return _err(state, "NOT_SAID_BY_CALLER", NOT_SAID, ignored=ignored)

    # Look up both sides before reporting a failure, so the side that worked is kept and the
    # caller only repeats the other one ("From Atlantis to San Francisco": SF is saved).
    places: dict[str, Place | None] = {"origin": None, "destination": None}
    failure: tuple[str, str, str | None, CityToZipError] | None = None
    for side, city, st in (
        ("origin", origin_city, origin_state),
        ("destination", destination_city, destination_state),
    ):
        if not city:
            continue
        try:
            places[side] = await _geocode(services, city, st)
        except CityToZipError as exc:
            if exc.code in ("GEOCODE_FAILED", "MISSING_API_KEY"):
                return _err(state, "GEOCODING_UNAVAILABLE", ESCALATE)
            failure = failure or (side, city, st, exc)
    if failure:
        side, city, st, exc = failure
        hint = _GEO_HINTS.get(exc.code, "Ask them to repeat the {side} city and state.")
        if canonicalize_state(city):
            # "I'm moving to Oregon" (Sergio's call, 2026-11-11): a state, not a city.
            hint = (
                f"They named the state, {city}, not a city. Ask which city in {city} "
                "(don't say you couldn't find it)."
            )
        state.set_route(places["origin"], places["destination"])
        return _failed(
            state,
            "route",
            exc.code,
            hint.format(city=city, state=st or "that state", side=side),
            failed=side,
            heard={"city": city, "state": st},
        )

    origin = places["origin"] or state.origin
    destination = places["destination"] or state.destination
    if origin and destination and origin.zip == destination.zip:
        return _err(
            state,
            "SAME_ORIGIN_AND_DESTINATION",
            "The origin and destination are the same place. Ask them to confirm both cities.",
        )
    state.set_route(places["origin"], places["destination"])
    state.failures["route"] = 0
    for side, place in places.items():
        if place:
            state.states_without_city.pop(side, None)
    saved = {side: p.spoken for side, p in places.items() if p}
    extra = {"ignored_not_said": ignored} if ignored else {}
    return _ok(state, _next_question(state), saved=saved, **extra)


# --- vehicles ----------------------------------------------------------------------------


def _vehicle_hint(exc: VehicleError, unsure: bool = False) -> str:
    """What to ask. The body type comes up only once the caller said they don't know
    (CONVERSATION_DESIGN.md: make only -> year and model; "I don't know" -> sedan, SUV or
    pickup); offered earlier, gpt-oss jumped to it and quoted an estimate."""
    k = exc.known
    name = " ".join(str(k[x]) for x in ("year", "make", "model") if k.get(x)) or "the vehicle"
    options = ", ".join(exc.options)
    fallback = (
        " They don't know it: ask whether it's a sedan, SUV or pickup and call save_vehicle "
        "again with vehicle_type."
        if unsure
        else ""
    )
    match exc.code:
        case VehicleErrorCode.MISSING_MAKE_AND_MODEL:
            return "Ask for the make and model of the vehicle." + fallback
        case VehicleErrorCode.MISSING_MODEL:
            ask = "model" if k.get("year") else "year and model"
            return f"Ask for the {ask} of the {name}." + fallback
        case VehicleErrorCode.MISSING_YEAR:
            return f"Ask what year the {name} is." + fallback
        case VehicleErrorCode.MAKE_NOT_FOUND:
            extra = f" Close matches: {options}." if options else ""
            return (
                f"Say you couldn't find that make in our system and ask them to repeat it.{extra}"
            )
        case VehicleErrorCode.MODEL_NOT_FOUND:
            extra = f" Close matches: {options}." if options else ""
            return (
                f"Say you couldn't find that model for the {name} in our system and ask if you "
                f"got a detail wrong.{extra}"
            )
        case VehicleErrorCode.AMBIGUOUS_MODEL | VehicleErrorCode.AMBIGUOUS_MAKE:
            return f"Ask which one it is: {options}."
        case VehicleErrorCode.YEAR_NOT_AVAILABLE | VehicleErrorCode.NO_TRIMS:
            years = exc.to_dict().get("available_years")
            span = f" Our system has it from {years['from']} to {years['to']}." if years else ""
            return f"Say you couldn't find that year for the {name} and double-check it.{span}"
    return "Ask them to repeat the year, make and model."


def _grounded(
    said: str | None, year: int | None, make: str | None, model: str | None, kind: str | None
) -> tuple[int | None, str | None, str | None, str | None, list[str]]:
    """Drop any vehicle detail the caller never said (grounding guardrail); None skips it."""
    ignored: list[str] = []
    if said is None:
        return year, make, model, kind, ignored
    if year is not None and not grounding.year_said(year, said):
        ignored.append(f"year {year}")
        year = None
    if make and not grounding.make_said(make, said):
        ignored.append(f"make {make}")
        make = None
    if model and not grounding.model_said(model, said):
        ignored.append(f"model {model}")
        model = None
    if kind and not grounding.vehicle_type_said(kind, said):
        ignored.append(f"type {kind}")
        kind = None
    return year, make, model, kind, ignored


# Vehicle errors that mean "we couldn't find what they said" (not "they haven't said it yet").
_NOT_FOUND = {
    VehicleErrorCode.MAKE_NOT_FOUND,
    VehicleErrorCode.MODEL_NOT_FOUND,
    VehicleErrorCode.YEAR_NOT_AVAILABLE,
    VehicleErrorCode.NO_TRIMS,
}


async def _resolve_vehicle(
    state: QuoteSession,
    services: Services,
    *,
    year: int | None,
    make: str | None,
    model: str | None,
    vehicle_type: str | None,
    operational: bool,
    unsure: bool = True,
) -> tuple[dict[str, Any] | None, Result | None]:
    """Year/make/model -> the fields of a ``VehicleEntry`` (plus ``_estimate`` and
    ``_heard_as``), or the error result that tells Mia what to ask."""
    try:
        v = await services.resolver.resolve(year=year, make=make, model=model)
    except VehicleError as exc:
        kind = normalize_vehicle_type(vehicle_type)
        missing_codes = (
            VehicleErrorCode.MISSING_MAKE_AND_MODEL,
            VehicleErrorCode.MISSING_MODEL,
            VehicleErrorCode.MISSING_YEAR,
        )
        if kind and exc.code in missing_codes and unsure:
            fields = {
                "year": normalize_year(year),
                "make": exc.known.get("make"),
                "model": exc.known.get("model"),
                "vehicle_type": kind,
                "operational": operational,
                "_estimate": kind,
            }
            return fields, None
        if vehicle_type and not kind:
            return None, _err(
                state,
                "UNKNOWN_VEHICLE_TYPE",
                "Ask whether it's a sedan, SUV, pickup, van, minivan, coupe, convertible, "
                "hatchback or wagon.",
            )
        if exc.code in _NOT_FOUND:
            return None, _failed(
                state, "vehicle", str(exc.code), _vehicle_hint(exc), **exc.to_dict()
            )
        return None, _err(state, str(exc.code), _vehicle_hint(exc, unsure), **exc.to_dict())
    except CarHaulerError as exc:
        return None, _err(state, str(exc.code), ESCALATE)
    state.failures["vehicle"] = 0
    fields = {
        "year": v.year,
        "make": v.make,
        "model": v.model,
        "trim_id": v.trim_id,
        "trim_name": v.trim_name,
        "operational": operational,
        "_heard_as": v.corrections or None,
    }
    return fields, None


def _entry_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if not k.startswith("_")}


def _estimate_note(fields: dict[str, Any]) -> str:
    kind = fields.get("_estimate")
    if not kind:
        return ""
    return (
        f"Tell them you'll quote it as a typical {'SUV' if kind == 'suv' else kind}, so the "
        "price is an estimate. "
    )


# "No wait, never mind, keep the Civic": gpt-oss called undo_last_change and save_vehicle in
# the same step (stage 8 scenario, 2026-11-10), so the Civic came back twice. The guardrail
# checks both before either runs, so the duplicate is caught here, once the undo has run.
ALREADY_ON_FILE = (
    "That vehicle is already on file, so nothing was added. If they have two of the same, "
    "ask how many vehicles in total. "
)


def _already_on_file(state: QuoteSession, fields: dict[str, Any]) -> bool:
    """The same vehicle is on file and the caller never said they ship more than we have."""
    same = ("year", "make", "model", "trim_id", "vehicle_type")
    if len(state.vehicles) < (state.expected_vehicles or 1):
        return False
    return any(all(getattr(v, k) == fields.get(k) for k in same) for v in state.vehicles)


async def model_from_words(
    services: Services, make: str, said: str, *, alone: bool = False
) -> str | None:
    """The catalog model of ``make`` the caller named, longest name first ("Civic del Sol"
    before "Civic"); None if none or the catalog can't be read. ``alone``: also a short answer
    that is only the model ("Corolla."), for when Mia just asked for it."""
    try:
        names = await services.resolver.model_names(make)
    except Exception:
        return None
    for name in sorted(names, key=len, reverse=True):
        if grounding.model_named(name, make, said) or (alone and grounding.model_alone(name, said)):
            return name
    return None


async def save_vehicle(
    state: QuoteSession,
    services: Services,
    *,
    year: int | None = None,
    make: str | None = None,
    model: str | None = None,
    vehicle_type: str | None = None,
    drivable: bool | None = True,
    total_vehicles: int | None = None,
    said: str | None = None,
    last_said: str | None = None,
    unsure: bool = True,
) -> Result:
    """``said``: everything the caller said so far, for the grounding check (None skips it).
    ``last_said``: their latest message; a year they corrected in it ("twenty ten... twenty
    twenty") becomes the one they settled on, whatever the model passed. ``unsure``: the caller
    said they don't know the model (or answered Mia's sedan/SUV/pickup question), so a body
    type may be quoted as an estimate."""
    _note_vehicle_count(state, said)
    if last_said:
        year = grounding.corrected_year(year, last_said)
        named = grounding.makes_named(last_said)
        if named >= 2 and named > (state.expected_vehicles or 0):
            state.expected_vehicles = named  # so Mia asks for the one the model skipped
    # What the caller already said of this vehicle (an earlier turn), if the model left it out.
    # Always, even with a vehicle_type: gpt-oss sent save_vehicle(year, vehicle_type="sedan")
    # without the Toyota it had heard (scenario estimate_after_unsure).
    unsure = unsure or bool(state.partial_vehicle.get("model_unknown"))
    if state.partial_vehicle:
        year = year or state.partial_vehicle.get("year")
        make = make or state.partial_vehicle.get("make")
    # Models send null for "not mentioned": only an explicit False means it doesn't run.
    operational = drivable is not False
    if make and model and normalize(model) == normalize(make):
        model = None  # "a Jeep" -> save_vehicle(make="Jeep", model="Jeep") (2026-11-11)
    year, make, model, vehicle_type, ignored = _grounded(said, year, make, model, vehicle_type)
    if ignored and not (year or make or model or vehicle_type):
        return _err(state, "NOT_SAID_BY_CALLER", NOT_SAID, ignored=ignored)
    if make and not model and not vehicle_type and said:
        # The caller said the model but the LLM left it out ("my twenty twenty Honda Civic"
        # -> save_vehicle(2020, Honda): Mia asked "What model is the 2020 Honda?").
        model = await model_from_words(services, make, said)
    # The count only if the caller said it ("two cars"): with "it's a twenty ten, twenty twenty
    # 4Runner" gpt-oss passed total_vehicles=2 and Mia asked for a second car (stage 8 test).
    if total_vehicles and total_vehicles > 0:
        if said is None or grounding.vehicle_count_said(said) == total_vehicles:
            state.expected_vehicles = total_vehicles
    fields, error = await _resolve_vehicle(
        state,
        services,
        year=year,
        make=make,
        model=model,
        vehicle_type=vehicle_type,
        operational=operational,
        unsure=unsure,
    )
    if error:
        if ignored and error.get("error_code", "").startswith("MISSING"):
            # A detail they gave was dropped as not said (e.g. a model the guardrail didn't
            # match). Ask as usual, but count it: asking forever is worse than a person
            # (13 tries on 2026-11-11). The third time in a row, offer a representative.
            state.failures["vehicle"] = state.failures.get("vehicle", 0) + 1
            error["ignored_not_said"] = ignored
            if state.failures["vehicle"] >= MAX_FAILURES:
                return _err(
                    state,
                    error["error_code"],
                    STILL_NOT_FOUND,
                    ignored_not_said=ignored,
                    attempts=state.failures["vehicle"],
                )
        return error
    assert fields is not None
    if _already_on_file(state, _entry_fields(fields)):
        return _ok(state, ALREADY_ON_FILE + _next_question(state), saved=None)
    entry = state.add_vehicle(**_entry_fields(fields))
    state.partial_vehicle = {}
    saved: dict[str, Any] = {"quote_id": entry.quote_id, "vehicle": entry.label}
    if fields.get("_estimate"):
        saved["estimate"] = True
    if fields.get("_heard_as"):
        saved["heard_as"] = fields["_heard_as"]
    return _ok(state, _estimate_note(fields) + _next_question(state), saved=saved)


# --- changes (stage 8) -------------------------------------------------------------------
# Changing, removing or restoring a vehicle (a route change is save_origin_destination again).
# Each change sends the old version to the trash (state.py) and drops the last quote, so Mia
# reads everything back and quotes again once the caller confirms.

ASK_WHICH = (
    "They have more than one vehicle: ask which one they mean, using each vehicle's name, "
    "then call this again with its quote_id."
)


def _pick_vehicle(state: QuoteSession, quote_id: str | None) -> Result | Any:
    if quote_id:
        found = state.find_vehicle(quote_id)
        if found:
            return found
    if not quote_id and len(state.vehicles) == 1:
        return state.vehicles[0]
    if not state.vehicles:
        return _err(
            state, "NO_VEHICLES", "There's no vehicle on file yet. " + _next_question(state)
        )
    return _err(state, "WHICH_VEHICLE", ASK_WHICH)


async def update_vehicle(
    state: QuoteSession,
    services: Services,
    *,
    quote_id: str | None = None,
    year: int | None = None,
    make: str | None = None,
    model: str | None = None,
    vehicle_type: str | None = None,
    drivable: bool | None = None,
    said: str | None = None,
    last_said: str | None = None,
) -> Result:
    """The caller changed a vehicle ("actually it's a 2021", "it's a Toyota 4Runner, not the
    Civic"). Only what they changed is passed; the rest stays. A new make drops the old model
    (a Toyota isn't a Civic)."""
    target = _pick_vehicle(state, quote_id)
    if isinstance(target, dict):
        return target
    if last_said:
        year = grounding.corrected_year(year, last_said)
    year, make, model, vehicle_type, ignored = _grounded(said, year, make, model, vehicle_type)
    if not (year or make or model or vehicle_type) and drivable is None:
        return _err(
            state,
            "NOT_SAID_BY_CALLER" if ignored else "NOTHING_TO_CHANGE",
            NOT_SAID if ignored else "Ask what they'd like to change about the vehicle.",
            ignored=ignored,
        )
    new_make = make or target.make
    same_make = (new_make or "").lower() == (target.make or "").lower()
    new_model = model or (target.model if same_make else None)
    fields, error = await _resolve_vehicle(
        state,
        services,
        year=year or target.year,
        make=new_make,
        model=new_model,
        vehicle_type=vehicle_type or (target.vehicle_type if not model else None),
        operational=target.operational if drivable is None else drivable is not False,
    )
    if error:
        return error
    assert fields is not None
    before = target.label
    entry = state.replace_vehicle(target.quote_id, **_entry_fields(fields))
    return _ok(
        state,
        f"Tell them you've changed the {before} to the {entry.label}. "
        + _estimate_note(fields)
        + _next_question(state),
        updated={"from": before, "to": entry.label, "quote_id": entry.quote_id},
    )


async def remove_vehicle(
    state: QuoteSession, services: Services, *, quote_id: str | None = None
) -> Result:
    """The caller isn't shipping one of their vehicles after all."""
    if len(state.vehicles) == 1 and (not quote_id or state.find_vehicle(quote_id)):
        return _err(
            state,
            "ONLY_VEHICLE",
            "That's their only vehicle, so it can't be removed: ask which vehicle they want to "
            "ship instead (then use update_vehicle), or if they'd rather not ship anything.",
        )
    target = _pick_vehicle(state, quote_id)
    if isinstance(target, dict):
        return target
    priced = state.priced if state.quote else []
    state.remove_vehicle(target.quote_id)
    removed = {"vehicle": target.label, "quote_id": target.quote_id}
    # Belinda, 2026-11-11 (call fa3b77253965): after the quote, removing the Toyota made Mia
    # read everything back and quote again, but each vehicle was already priced on its own for
    # this route. What's left is repriced from that quote: no read-back, no new API call.
    left = [q for q in priced if state.find_vehicle(q.request.quote_id)]
    if left and len(left) == len(state.vehicles):
        summary = _store_quote(state, left)
        # "Your new estimated cost for the Honda is $881." (one left), or the usual breakdown.
        new = "Your new estimated cost"
        if len(summary.items) == 1:
            new += f" for {summary.items[0][0]}"
        say = summary.speech.replace("Your estimated cost", new, 1)
        return _ok(
            state,
            f"Tell them you've removed the {target.label}. Then: " + _after_quote(state),
            removed=removed,
            say=say,
            total=summary.total,
            transit=_transit(summary),
        )
    return _ok(
        state,
        f"Tell them you've removed the {target.label}. " + _next_question(state),
        removed=removed,
    )


async def undo_last_change(state: QuoteSession, services: Services) -> Result:
    """The caller changed their mind back ("actually, keep the Honda")."""
    item = state.undo_last_change()
    if item is None:
        return _err(state, "NOTHING_TO_UNDO", "Nothing has changed yet. Ask what they'd like.")
    what = "the route" if item.kind == "route" else "the vehicle"
    return _ok(state, f"Tell them you've put back {what}. " + _next_question(state))


# --- quote -------------------------------------------------------------------------------

_QUOTE_ERROR_HINTS = {
    ErrorCode.INVALID_ORIGIN_ZIP: (
        "Say there was a problem with the pickup city; ask them to repeat it."
    ),
    ErrorCode.INVALID_DESTINATION_ZIP: (
        "Say there was a problem with the delivery city; ask them to repeat it."
    ),
    ErrorCode.SAME_ZIP: "The origin and destination are the same; ask them to confirm both.",
}


async def get_quote(
    state: QuoteSession, services: Services, *, last_said: str | None = None
) -> Result:
    """``last_said``: the caller's latest message; the quote needs their yes (None skips it)."""
    if state.missing:
        return _err(
            state,
            "MISSING_INFO",
            "Not everything is saved yet. If the caller already said it, save it now with "
            "save_vehicle or save_origin_destination. Otherwise: " + _next_question(state),
            missing=state.missing,
        )
    # Guardrail: quote only right after the caller confirmed the read-back.
    if last_said is not None and not grounding.is_confirmation(last_said):
        return _err(
            state,
            "NOT_CONFIRMED",
            "Don't quote yet. Read back everything on file in one sentence (each vehicle, origin "
            "and destination with states) and ask if it's correct.",
        )
    assert state.origin and state.destination
    state.advance(Stage.CONFIRM)
    filler = phrases.pick(state, "filler", phrases.FILLER)
    pause = services.before_quote(filler) if services.before_quote else None
    result = await _quote(state, services)
    # The price waits for the filler and the typing sound, so it feels calculated (Sergio's
    # call, 2026-11-09); never more than a few seconds even if the audio hangs.
    if inspect.isawaitable(pause):
        try:
            await asyncio.wait_for(pause, timeout=MAX_QUOTE_PAUSE_SECONDS)
        except TimeoutError:
            pass
    return result


FILLER = phrases.FILLER[0]  # one of phrases.FILLER is said
MAX_QUOTE_PAUSE_SECONDS = 8.0


async def _quote(state: QuoteSession, services: Services) -> Result:
    assert state.origin and state.destination
    requests = [
        QuoteRequest(
            from_zip=state.origin.zip,
            to_zip=state.destination.zip,
            trim_id=v.trim_id,
            vehicle_type=None if v.trim_id else (v.vehicle_type or "sedan"),
            year=v.year,
            make=v.make,
            model=v.model,
            operational=v.operational,
            quote_id=v.quote_id,
        )
        for v in state.vehicles
    ]
    try:
        quotes = await quote_vehicles(services.carhauler, requests)
    except CarHaulerError as exc:
        hint = _QUOTE_ERROR_HINTS.get(exc.code, ESCALATE)
        return _err(state, str(exc.code), hint)

    summary = _store_quote(state, quotes)
    return _ok(
        state,
        _after_quote(state),
        say=summary.speech,
        total=summary.total,
        transit=_transit(summary),
    )


def _transit(summary: Any) -> str | None:
    days = summary.transit_days
    return f"{days[0]} to {days[1]} days door to door" if days else None


def _store_quote(state: QuoteSession, quotes: list[Any]) -> Any:
    """Keep a quote (one priced VehicleQuote per vehicle) as the one on file."""
    summary = summarize(quotes)
    transit = summary.transit_days
    state.priced = list(quotes)
    state.quote = {
        "total": summary.total,
        "items": [{"vehicle": label, "price": price} for label, price in summary.items],
        "per_vehicle": [
            {"quote_id": q.request.quote_id, "price": q.price, "distance": q.quote.distance}
            for q in quotes
        ],
        "transit_days": list(transit) if transit else None,
        "estimate": any(v.is_estimate for v in state.vehicles),
    }
    state.advance(Stage.QUOTED)
    return summary


def _after_quote(state: QuoteSession) -> str:
    """What Mia does once she has a price. Sergio, 2026-11-11: after a "no" to the
    representative, don't ask "anything else?"; close the call (end_call's `next` has the
    closing line). A question still gets answered. The offer's wording varies (phrases.py)."""
    offer = phrases.pick(state, "offer", phrases.OFFER)
    after = (
        "Read `say` to the caller word for word (don't change any numbers). Then ask, in these "
        f'words: "{offer}" If they say no, or say goodbye, call end_call (do not ask if '
        "there's anything else). If they ask a question, answer it first."
    )
    if state.quote and state.quote["estimate"]:
        after = "Mention the price is an estimate based on the vehicle type. " + after
    return after


# --- people ------------------------------------------------------------------------------


def transfer_kind(state: QuoteSession, *, asked: bool) -> str:
    """The transfer's disposition: "forced" after a tool failure Mia couldn't fix, "requested"
    when the caller asked for a person unprompted, "organic" when they said yes to Mia's offer
    (normally after the quote: the happy path)."""
    if state.escalated:
        return "forced"
    return "requested" if asked else "organic"


async def request_human(
    state: QuoteSession, services: Services, *, reason: str = "", asked: bool = True
) -> Result:
    """Connect the caller with a licensed representative: a phone transfer on voice calls
    with a trunk (transfer.py), otherwise just noted. ``asked``: the caller asked on their own
    (False: they said yes to Mia's offer)."""
    state.human_requested = True
    state.human_request_reason = reason or None
    state.transfer_kind = state.transfer_kind or transfer_kind(state, asked=asked)
    state.advance(Stage.TRANSFER)
    if state.transfer in ("pending", "connected"):
        return _ok(state, "You're already connecting them. Say nothing else.", transferring=True)
    if services.transfer is None:
        return _ok(
            state,
            "Tell them a licensed representative isn't available on this line right now, and "
            "ask if there's anything else you can help with.",
            transferring=False,
        )
    state.transfer = "pending"
    return _ok(
        state,
        f'Say exactly this and nothing else: "{transfer.CONNECTING}"',
        transferring=True,
    )


async def end_call(state: QuoteSession, services: Services) -> Result:
    """Marks the call as ended. The hang-up itself (``services.end_call``) happens in
    agent.py after the goodbye has been spoken, so the caller hears it."""
    state.ended = True
    state.end_reason = state.end_reason or "mia"
    if state.end_reason == "off_topic":
        # note_off_topic ended it in the same step: keep its goodbye, which says why.
        return _ok(state, OFF_TOPIC_GOODBYE)
    closing = phrases.pick(state, "closing", phrases.CLOSING)
    return _ok(state, f'Say exactly this and nothing else: "{closing}"')


# Sergio, 2026-11-11: "Sure, let us know. Feel free to call again if you want to get another
# quote. Have a nice day." One of phrases.CLOSING is said.
CLOSING = phrases.CLOSING[0]


# --- off-topic (stage 8) -----------------------------------------------------------------

OFF_TOPIC_GOODBYE = (
    "Say politely that you can only help with car shipping quotes, thank them for calling F&F "
    "and say goodbye. Don't transfer them."
)


async def note_off_topic(state: QuoteSession, services: Services) -> Result:
    """The caller asked something unrelated to car shipping (a joke, trivia, nonsense). Mia
    answers in a few words and steers back; the third time she ends the call politely, never
    with a transfer (docs/CONVERSATION_DESIGN.md, adversarial path)."""
    state.off_topic += 1
    state.off_topic_turns.append(state.caller_turns)
    if state.off_topic >= OFF_TOPIC_LIMIT:
        state.ended, state.end_reason = True, "off_topic"
        state.hang_up_after_speech = True  # voice: hang up once this line has played
        return _ok(
            state,
            OFF_TOPIC_GOODBYE,
            off_topic=state.off_topic,
        )
    return _ok(
        state,
        "Answer in a few words at most, without making anything up, then steer back to the "
        "quote: " + _next_question(state),
        off_topic=state.off_topic,
    )
