"""Everything Mia knows about the current call (``AgentSession.userdata``).

Tools read and change this; nothing else does. ``snapshot()`` is what the tools return as "on
file", and later what the live panel and the call record show.

Quote IDs (docs/CONVERSATION_DESIGN.md): every vehicle gets one. Updating or removing a vehicle
moves the old entry to the ``trash`` and the updated vehicle gets a new ID, so a previous state
can be restored if the caller changes their mind.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Stage(StrEnum):
    """How far the call got (for 'why did they leave' on the dashboard)."""

    GREETING = "greeting"
    ROUTE = "route"
    VEHICLES = "vehicles"
    CONFIRM = "confirm"
    QUOTED = "quoted"
    TRANSFER = "transfer"


@dataclass
class Place:
    city: str
    state: str  # 2-letter code
    state_name: str
    zip: str

    @property
    def spoken(self) -> str:
        return f"{self.city}, {self.state_name}"


@dataclass
class VehicleEntry:
    quote_id: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim_id: int | None = None
    trim_name: str | None = None
    vehicle_type: str | None = None  # set when quoting by body type only
    operational: bool = True
    saved_turn: int = 0  # caller turn it was saved in (duplicate-save guard)

    @property
    def label(self) -> str:
        parts = [str(self.year) if self.year else None, self.make, self.model]
        named = " ".join(p for p in parts if p)
        if self.trim_id:
            return named
        kind = "SUV" if self.vehicle_type == "suv" else (self.vehicle_type or "vehicle")
        return f"{named} {kind}".strip() if named else kind

    @property
    def is_estimate(self) -> bool:
        return self.trim_id is None


@dataclass
class TrashItem:
    kind: str  # "vehicle" | "route" | "quote"
    data: dict[str, Any]
    reason: str
    at: float = field(default_factory=time.time)


TYPE_QUESTION = "No problem. Is it a sedan, an SUV, or a pickup?"


@dataclass
class QuoteSession:
    origin: Place | None = None
    destination: Place | None = None
    vehicles: list[VehicleEntry] = field(default_factory=list)
    expected_vehicles: int | None = None  # "I need to ship 2 cars"
    trash: list[TrashItem] = field(default_factory=list)
    stage: Stage = Stage.GREETING
    quote: dict[str, Any] | None = None  # last quote given: total, items, transit_days
    human_requested: bool = False
    human_request_reason: str | None = None
    # Phone transfer (transfer.py): "pending", "connected", "no_answer", "limit" (daily cap) or
    # None (not tried; e.g. text chat, or no trunk configured).
    transfer: str | None = None
    # Why it was transferred (the disposition): "organic" (said yes to Mia's offer, the happy
    # path), "requested" (asked for a person unprompted) or "forced" (a tool failed and Mia
    # offered a representative). Set by request_human.
    transfer_kind: str | None = None
    # A tool failed in a way Mia can't fix (API down, out of calls): she offers a person.
    escalated: bool = False
    # Failures in a row per detail ("route", "vehicle"): the third offers a person (stage 8).
    failures: dict[str, int] = field(default_factory=dict)
    # Unrelated or joke questions (note_off_topic): the third ends the call politely.
    off_topic: int = 0
    off_topic_turns: list[int] = field(default_factory=list)  # caller turns that counted
    # "from Miami to California": the side with a state but no city, so Mia asks for the city.
    states_without_city: dict[str, str] = field(default_factory=dict)
    ended: bool = False
    # Who ended it: "mia" (end_call or her goodbye), "time_limit", "caller" (hung up first) or
    # "silence" (the caller stopped answering; silence.py).
    end_reason: str | None = None
    # Mia said goodbye without calling end_call: hang up once that line has been spoken.
    hang_up_after_speech: bool = False
    # Tool calls the output guardrail dropped (invented details, unconfirmed quote).
    dropped_calls: list[dict[str, Any]] = field(default_factory=list)
    caller_turns: int = 0  # how many times the caller has spoken
    # Year and make the caller said for the vehicle in progress, before its model (Sergio's
    # call, 2026-11-10: "from Miami to Chicago. It's a twenty twenty Honda", then asked for
    # the year, make and model again). Merged into the next save_vehicle, then cleared.
    partial_vehicle: dict[str, Any] = field(default_factory=dict)
    # Tool calls code made itself (agent.llm_node), as "name@turn": at most once per caller
    # turn, or a failure (CarHauler down at the quote) would make code retry every step.
    code_calls: set[str] = field(default_factory=set)
    _next_id: int = 1

    # --- quote IDs and the trash ---------------------------------------------------------

    def new_quote_id(self) -> str:
        qid = f"Q{self._next_id}"
        self._next_id += 1
        return qid

    def add_vehicle(self, **fields: Any) -> VehicleEntry:
        entry = VehicleEntry(quote_id=self.new_quote_id(), saved_turn=self.caller_turns, **fields)
        self.vehicles.append(entry)
        self._invalidate_quote("vehicle added")
        self.advance(Stage.VEHICLES)
        return entry

    def find_vehicle(self, quote_id: str) -> VehicleEntry | None:
        return next((v for v in self.vehicles if v.quote_id == quote_id), None)

    def _invalidate_quote(self, reason: str) -> None:
        if self.quote is not None:
            self.trash.append(TrashItem("quote", self.quote, reason))
            self.quote = None

    def set_route(self, origin: Place | None, destination: Place | None) -> None:
        changed = (origin and self.origin and origin.zip != self.origin.zip) or (
            destination and self.destination and destination.zip != self.destination.zip
        )
        if changed:
            self.trash.append(
                TrashItem(
                    "route",
                    {
                        "origin": asdict(self.origin) if self.origin else None,
                        "destination": asdict(self.destination) if self.destination else None,
                    },
                    "route changed",
                )
            )
            self._invalidate_quote("route changed")
        self.origin = origin or self.origin
        self.destination = destination or self.destination
        self.advance(Stage.ROUTE)

    # --- changes (stage 8): every one goes through the trash, so undo can restore it --------

    def replace_vehicle(self, quote_id: str, **fields: Any) -> VehicleEntry:
        """The caller changed a vehicle: the old entry goes to the trash, the new one takes its
        place with a new quote ID."""
        old = self.find_vehicle(quote_id)
        assert old is not None
        i = self.vehicles.index(old)
        entry = VehicleEntry(quote_id=self.new_quote_id(), saved_turn=self.caller_turns, **fields)
        self.vehicles[i] = entry
        self.trash.append(
            TrashItem(
                "vehicle",
                {"vehicle": asdict(old), "position": i, "replaced_by": entry.quote_id},
                "vehicle updated",
            )
        )
        self._invalidate_quote("vehicle updated")
        return entry

    def remove_vehicle(self, quote_id: str) -> VehicleEntry:
        old = self.find_vehicle(quote_id)
        assert old is not None
        i = self.vehicles.index(old)
        self.vehicles.remove(old)
        self.trash.append(
            TrashItem("vehicle", {"vehicle": asdict(old), "position": i}, "vehicle removed")
        )
        if self.expected_vehicles and self.expected_vehicles > len(self.vehicles):
            self.expected_vehicles = len(self.vehicles) or None
        self._invalidate_quote("vehicle removed")
        return old

    def undo_last_change(self) -> TrashItem | None:
        """Put back what the last vehicle or route change replaced ("actually, keep the
        Honda"). The current version goes to the trash in turn, so undo can be undone."""
        for k in range(len(self.trash) - 1, -1, -1):
            item = self.trash[k]
            if item.kind not in ("vehicle", "route"):
                continue
            del self.trash[k]
            if item.kind == "route":
                current = {
                    "origin": asdict(self.origin) if self.origin else None,
                    "destination": asdict(self.destination) if self.destination else None,
                }
                self.origin = Place(**item.data["origin"]) if item.data["origin"] else None
                self.destination = (
                    Place(**item.data["destination"]) if item.data["destination"] else None
                )
                self.trash.append(TrashItem("route", current, "undone"))
            else:
                old = VehicleEntry(**item.data["vehicle"])
                replaced = item.data.get("replaced_by")
                now = self.find_vehicle(replaced) if replaced else None
                if now is not None:
                    i = self.vehicles.index(now)
                    self.vehicles[i] = old
                    self.trash.append(
                        TrashItem(
                            "vehicle",
                            {"vehicle": asdict(now), "position": i, "replaced_by": old.quote_id},
                            "undone",
                        )
                    )
                else:
                    i = min(item.data.get("position", len(self.vehicles)), len(self.vehicles))
                    self.vehicles.insert(i, old)
                    if self.expected_vehicles and self.expected_vehicles < len(self.vehicles):
                        self.expected_vehicles = len(self.vehicles)
            self._invalidate_quote("change undone")
            return item
        return None

    # --- progress ------------------------------------------------------------------------

    def advance(self, stage: Stage) -> None:
        """Stages only move forward; this is the furthest point the call reached."""
        order = list(Stage)
        if order.index(stage) > order.index(self.stage):
            self.stage = stage

    @property
    def missing(self) -> list[str]:
        out = []
        if not self.origin:
            out.append("origin")
        if not self.destination:
            out.append("destination")
        if not self.vehicles:
            out.append("vehicle")
        elif self.expected_vehicles and len(self.vehicles) < self.expected_vehicles:
            out.append(f"vehicle {len(self.vehicles) + 1} of {self.expected_vehicles}")
        return out

    def snapshot(self) -> dict[str, Any]:
        """What's on file, compact enough to hand back to the LLM in every tool result."""
        return {
            "origin": self.origin.spoken if self.origin else None,
            "destination": self.destination.spoken if self.destination else None,
            "vehicles": [
                {"quote_id": v.quote_id, "vehicle": v.label}
                | ({"estimate_by_type": True} if v.is_estimate else {})
                | ({} if v.operational else {"drivable": False})
                for v in self.vehicles
            ],
            "expected_vehicles": self.expected_vehicles,
            "missing": self.missing,
        } | ({"heard_so_far": self.partial_label()} if self.partial_vehicle else {})

    def code_ran_once(self, name: str) -> bool:
        """True the first time this turn (and remembers it), False after that."""
        key = f"{name}@{self.caller_turns}"
        if key in self.code_calls:
            return False
        self.code_calls.add(key)
        return True

    def partial_label(self) -> str:
        """ "2020 Honda", "2020 car", "Honda": what the caller said of the next vehicle."""
        p = self.partial_vehicle
        if p.get("make"):
            return " ".join(str(x) for x in (p.get("year"), p["make"]) if x)
        return f"{p['year']} car" if p.get("year") else ""

    def partial_question(self) -> str:
        """The question for what's still missing of the vehicle in progress. Once they said they
        don't know the model, it's the body type (CONVERSATION_DESIGN slot rules)."""
        p = self.partial_vehicle
        if p.get("model_unknown"):
            return TYPE_QUESTION
        if p.get("year") and p.get("make"):
            return f"What model is the {p['year']} {p['make']}?"
        if p.get("make"):
            return f"What year and model is the {p['make']}?"
        return f"What's the make and model of the {p['year']} car?"

    def note_partial_vehicle(self, heard: dict[str, Any]) -> None:
        """Keep what the caller said of the vehicle in progress (newer values win)."""
        self.partial_vehicle = {**self.partial_vehicle, **heard}

    def to_record(self) -> dict[str, Any]:
        """Full state for logs and the call record (records.py)."""
        return {
            "origin": asdict(self.origin) if self.origin else None,
            "destination": asdict(self.destination) if self.destination else None,
            "vehicles": [asdict(v) for v in self.vehicles],
            "trash": [asdict(t) for t in self.trash],
            "stage": str(self.stage),
            "quote": self.quote,
            "human_requested": self.human_requested,
            "transfer": self.transfer,
            "transfer_kind": self.transfer_kind,
            "escalated": self.escalated,
            "off_topic": self.off_topic,
            "dropped_calls": self.dropped_calls,
            "caller_turns": self.caller_turns,
            "end_reason": self.end_reason,
        }
