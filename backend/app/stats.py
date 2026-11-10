"""GET /api/stats: one compact row of facts per call, for the Stats view (stage 6).

The browser turns these rows into the KPIs, the funnel and the trends (in the viewer's time
zone, for whatever date range they pick), so the API only has to say, per call:

- which **milestones** it reached: ``route`` (origin and destination both on file),
  ``vehicles`` (at least one), ``quoted`` (a price was given), ``transfer`` (a licensed
  representative picked up: the qualified lead). Milestones, not the furthest stage: a caller
  can give the car before the cities, or ask for a person before any quote.
- ``disposition``: how the call ended (Sergio's lead-qualification dispositions):
  ``organic_transfer`` (yes to Mia's offer, the happy path), ``requested_transfer`` (asked for
  a person), ``forced_transfer`` (a tool failed and Mia handed over), ``hung_up_on_hold``
  (left while the transfer rang), ``hung_up`` (left before the end), ``not_interested``
  (finished without a transfer).
- ``mia_s``: the time Mia handled the call, i.e. time a person didn't have to spend. A
  transferred call counts only until the handoff.
- ``test``: scripted calls (``mia.smoke``, rooms ``smoke-*``), hidden by default.

The facts live on each call's list row (``CALLS`` / ``<started_at>#<room>``) with
``stats_v``. The worker writes them for new calls (agent/src/mia/records.py ``summary``);
rows saved before that are filled in here from the full record, once, the first time stats
load (at most ``BACKFILL_PER_REQUEST`` per request).
"""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import db, ratelimit

router = APIRouter(tags=["stats"])

STATS_V = 2
BACKFILL_PER_REQUEST = 50
MAX_CALLS = 2000
STATS_PER_IP_PER_HOUR = 300


class CallFacts(BaseModel):
    room: str
    started_at: str
    test: bool
    duration_s: float
    mia_s: float
    route: bool
    vehicles: bool
    quoted: bool
    transfer: bool
    # hung_up, not_interested, hung_up_on_hold, organic_transfer, requested_transfer or
    # forced_transfer (see facts_from_record).
    disposition: str
    e2e_p50_ms: float | None = None


def facts_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """The milestones and Mia's time from a full call record (records.py ``build``)."""
    events = record.get("events") or []
    tools_ok = {e.get("name") for e in events if e.get("type") == "tool" and e.get("ok")}
    transferred = record.get("transfer") == "connected"
    mia_s = float(record.get("duration_s") or 0)
    if transferred:
        handoff = [
            e["t"]
            for e in events
            if (e.get("type") == "tool" and e.get("name") == "dial_representative")
            or (e.get("type") == "turn" and e.get("kind") == "handoff")
        ]
        if handoff:
            mia_s = float(max(handoff))
    quoted = record.get("quote") is not None or "get_quote" in tools_ok
    # The call's disposition. Transfers that connected say why (older records don't: a
    # transfer after a quote was the offer, before it the caller asked).
    caller_left = record.get("end_reason") in ("caller", "silence")
    if transferred:
        kind = record.get("transfer_kind") or ("organic" if quoted else "requested")
        disposition = f"{kind}_transfer"
    elif record.get("transfer") in ("pending", "no_answer") and caller_left:
        disposition = "hung_up_on_hold"
    elif caller_left:
        disposition = "hung_up"
    else:
        disposition = "not_interested"
    return {
        "route": bool(record.get("origin") and record.get("destination")),
        "vehicles": bool(record.get("vehicles")) or "save_vehicle" in tools_ok,
        "quoted": quoted,
        "transfer": transferred,
        "disposition": disposition,
        "mia_s": round(mia_s, 1),
        "stats_v": STATS_V,
    }


def _all_rows() -> list[dict[str, Any]]:
    rows = db.latest("CALLS", MAX_CALLS)
    backfilled = 0
    for row in rows:
        if row.get("stats_v") == STATS_V or backfilled >= BACKFILL_PER_REQUEST:
            continue
        record = db.get(f"CALL#{row['room']}", "RECORD")
        if record is None:
            continue
        row.update(facts_from_record(record))
        db.put("CALLS", f"{row['started_at']}#{row['room']}", row)
        backfilled += 1
    return rows


@router.get("/api/stats")
def stats(request: Request, include_tests: bool = False) -> list[CallFacts]:
    if ratelimit.hit(f"stats-ip#{ratelimit.client_ip(request)}", 3600) > STATS_PER_IP_PER_HOUR:
        raise ratelimit.too_many("Too many requests. Try again in a bit.")
    out = []
    for row in _all_rows():
        if row.get("stats_v") != STATS_V:
            continue  # its record is missing; nothing to count
        test = row["room"].startswith("smoke-")
        if test and not include_tests:
            continue
        out.append(
            CallFacts(
                room=row["room"],
                started_at=row["started_at"],
                test=test,
                duration_s=float(row.get("duration_s") or 0),
                mia_s=float(row.get("mia_s") or 0),
                route=bool(row.get("route")),
                vehicles=bool(row.get("vehicles")),
                quoted=bool(row.get("quoted")),
                transfer=bool(row.get("transfer")),
                disposition=row.get("disposition") or "not_interested",
                e2e_p50_ms=row.get("e2e_p50_ms"),
            )
        )
    return out
