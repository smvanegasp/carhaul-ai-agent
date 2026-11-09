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
    ended: bool = False
    # Who ended it: "mia" (end_call), "time_limit" or "caller" (hung up first).
    end_reason: str | None = None
    # Tool calls the output guardrail dropped (invented details, unconfirmed quote).
    dropped_calls: list[dict[str, Any]] = field(default_factory=list)
    caller_turns: int = 0  # how many times the caller has spoken
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
        }

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
            "dropped_calls": self.dropped_calls,
            "caller_turns": self.caller_turns,
            "end_reason": self.end_reason,
        }
