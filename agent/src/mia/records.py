"""The call record: everything about one call, saved to DynamoDB when it ends.

One table (``TABLE_NAME``, default ``carhaul``) shared with the backend
(``backend/app/db.py``), keys ``pk``/``sk``:

- ``CALL#<room>`` / ``RECORD``: the full record (state, transcript, events, latency).
- ``CALLS`` / ``<started_at>#<room>``: a short summary, so the dashboard (stage 6) lists calls
  newest first with one query.
- ``CALL#<room>`` / ``FEEDBACK#...``: the caller's feedback (written by the backend).

The worker writes with its own AWS credentials (an ECS task role on AWS). Locally
``DYNAMODB_ENDPOINT`` points at DynamoDB Local (docker compose); with no ``TABLE_NAME`` and no
endpoint (a host ``dev`` worker without AWS) the record is only logged.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

from mia.events import CallEvents
from mia.state import QuoteSession

logger = logging.getLogger("mia.records")

# A record holds every event of a call up to 6 minutes; well under DynamoDB's 400 KB per item.
# If one ever grows past this, the events are left out (the transcript and state stay).
MAX_RECORD_BYTES = 350_000


def build(room: str, state: QuoteSession, events: CallEvents, **extra: Any) -> dict[str, Any]:
    started = datetime.fromtimestamp(events.started, UTC)
    duration = round(events.events[-1]["t"], 1) if events.events else 0.0
    tools = [e for e in events.events if e["type"] == "tool"]
    record = {
        "room": room,
        "started_at": started.isoformat(timespec="seconds"),
        "duration_s": duration,
        **state.to_record(),
        "transcript": events.transcript(),
        "talk_s": events.talk_seconds(),
        "interruptions": sum(
            1 for e in events.events if e["type"] == "turn" and e.get("interrupted")
        ),
        "tool_calls": len(tools),
        "tool_errors": sum(1 for e in tools if not e["ok"]),
        "latency": events.latency.summary(),
        "events": events.events,
        **extra,
    }
    if len(json.dumps(record, default=str)) > MAX_RECORD_BYTES:
        record["events"] = []
        record["events_dropped"] = True
    return record


def summary(record: dict[str, Any]) -> dict[str, Any]:
    """The few fields the call list needs."""
    quote = record.get("quote") or {}
    return {
        "room": record["room"],
        "started_at": record["started_at"],
        "duration_s": record["duration_s"],
        "stage": record["stage"],
        "end_reason": record["end_reason"],
        "human_requested": record["human_requested"],
        "transfer": record.get("transfer"),
        "vehicles": len(record["vehicles"]),
        "quote_total": quote.get("total"),
        "e2e_p50_ms": (record["latency"].get("e2e_latency") or {}).get("p50_ms"),
    }


# --- DynamoDB --------------------------------------------------------------------------------


def configured() -> bool:
    return bool(os.environ.get("TABLE_NAME") or os.environ.get("DYNAMODB_ENDPOINT"))


@lru_cache
def _table():
    import boto3  # only the worker needs it; text chat and most tests never get here

    resource = boto3.resource(
        "dynamodb",
        endpoint_url=os.environ.get("DYNAMODB_ENDPOINT") or None,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    return resource.Table(os.environ.get("TABLE_NAME", "carhaul"))


def _to_dynamo(value: Any) -> Any:
    """DynamoDB rejects Python floats; store them as Decimals."""
    return json.loads(json.dumps(value, default=str), parse_float=Decimal)


def save(record: dict[str, Any]) -> bool:
    """Write the record and its summary. Blocking (run it in a thread). Never raises."""
    if not configured():
        return False
    try:
        table = _table()
        room = record["room"]
        table.put_item(Item={"pk": f"CALL#{room}", "sk": "RECORD", **_to_dynamo(record)})
        table.put_item(
            Item={
                "pk": "CALLS",
                "sk": f"{record['started_at']}#{room}",
                **_to_dynamo(summary(record)),
            }
        )
        return True
    except Exception:
        logger.exception("couldn't save the call record for %s", record.get("room"))
        return False
