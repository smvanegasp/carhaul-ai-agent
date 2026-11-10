"""Transfer a browser caller to a licensed representative's phone (stage 9).

The caller is in a LiveKit room over WebRTC, so this isn't a SIP transfer (REFER only moves a
SIP caller). Mia **dials the representative into the same room** through the Twilio Elastic SIP
trunk, introduces the caller, and leaves; the two keep talking in the room until either hangs
up (main.py then deletes it). Set up the trunk with ``scripts/setup_twilio_trunk.py``.

Settings (repo-root .env locally, SSM ``/carhaul/agent/`` on AWS):

- ``TWILIO_SIP_ADDRESS``, ``TWILIO_SIP_USERNAME``, ``TWILIO_SIP_PASSWORD``: the trunk.
- ``TRANSFER_PHONE_NUMBER``: who Mia calls.
- ``TRANSFER_CALLER_ID``: what that phone shows: a verified caller ID in Twilio, so no Twilio
  number (no monthly fee). It must not be the number being called: a phone calling itself
  goes straight to voicemail (seen on the first test call, 2026-11-09).

Limits, because the site is public and every transfer rings a real phone: at most
``TRANSFERS_PER_DAY`` (5) a day, ``RING_SECONDS`` of ringing, ``MAX_TRANSFER_MINUTES`` (10) on
the phone. The trunk details travel inline with each call (``CreateSIPParticipantRequest.trunk``),
so there's no LiveKit trunk ID to keep in sync. The SDK's ``outbound_trunk_config=`` helper
fails on assignment in livekit-api 1.x, so the request sets ``trunk`` itself.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from mia.state import QuoteSession

logger = logging.getLogger("mia.transfer")

TRANSFERS_PER_DAY = int(os.environ.get("MIA_TRANSFERS_PER_DAY") or 5)
RING_SECONDS = 30
MAX_TRANSFER_MINUTES = 10
REPRESENTATIVE_IDENTITY = "representative"

# What Mia says (the tool's `next` asks for the first one; the rest are spoken by code).
CONNECTING = "Sure, I'll connect you with a licensed representative now. Please stay on the line."
NO_ANSWER = (
    "I'm sorry, I couldn't reach a licensed representative right now. Is there anything else I "
    "can help you with?"
)
UNAVAILABLE = (
    "I'm sorry, a licensed representative isn't available right now. Is there anything else I "
    "can help you with?"
)


@dataclass(frozen=True)
class Config:
    address: str
    username: str
    password: str
    phone: str
    caller_id: str

    @classmethod
    def from_env(cls) -> Config | None:
        """The transfer settings, or None if any is missing (then Mia only takes a note)."""
        values = {
            "address": os.environ.get("TWILIO_SIP_ADDRESS"),
            "username": os.environ.get("TWILIO_SIP_USERNAME"),
            "password": os.environ.get("TWILIO_SIP_PASSWORD"),
            "phone": os.environ.get("TRANSFER_PHONE_NUMBER"),
            "caller_id": os.environ.get("TRANSFER_CALLER_ID"),
        }
        if not all(values.values()):
            return None
        config = cls(**{k: v.strip() for k, v in values.items() if v})
        if config.caller_id == config.phone:
            logger.warning("TRANSFER_CALLER_ID equals the number called: it would hit voicemail")
            return None
        return config


def handoff_line(state: QuoteSession) -> str:
    """What Mia tells the representative once they pick up (the caller hears it too)."""
    parts = ["Hi, this is Mia from F&F. I have a caller here"]
    vehicles = [v.label for v in state.vehicles]
    if vehicles:
        what = vehicles[0] if len(vehicles) == 1 else f"{len(vehicles)} vehicles"
        parts.append(f" about shipping {'a ' if len(vehicles) == 1 else ''}{what}")
    if state.origin and state.destination:
        parts.append(f" from {state.origin.spoken} to {state.destination.spoken}")
    line = "".join(parts) + "."
    if state.quote and state.quote.get("total"):
        line += f" Their estimate was {state.quote['total']:,} dollars."
    return line + " I'll let you two talk now. Goodbye!"


# --- the daily cap ---------------------------------------------------------------------------

_local_count: dict[str, int] = {}


def take_slot(now: datetime | None = None) -> bool:
    """Count one transfer for today (UTC); False if today's cap is reached. Blocking.

    With DynamoDB configured the count is shared (one item per day, expires after 2 days);
    otherwise it's per process.
    """
    from mia import records

    day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
    if not records.configured():
        _local_count[day] = _local_count.get(day, 0) + 1
        return _local_count[day] <= TRANSFERS_PER_DAY
    try:
        expires = int((now or datetime.now(UTC)).timestamp()) + 2 * 86400
        item = records._table().update_item(
            Key={"pk": "TRANSFERS", "sk": day},
            UpdateExpression="ADD #n :one SET #ttl = :ttl",
            ExpressionAttributeNames={"#n": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={":one": 1, ":ttl": expires},
            ReturnValues="UPDATED_NEW",
        )
        return int(item["Attributes"]["count"]) <= TRANSFERS_PER_DAY
    except Exception:
        logger.exception("couldn't count the transfer; not transferring")
        return False


# --- dialing ---------------------------------------------------------------------------------


def dial_request(config: Config, room: str) -> Any:
    """The LiveKit request that rings the representative into ``room``."""
    from livekit import api
    from livekit.protocol.sip import SIPOutboundConfig

    return api.CreateSIPParticipantRequest(
        room_name=room,
        participant_identity=REPRESENTATIVE_IDENTITY,
        participant_name="Licensed representative",
        sip_call_to=config.phone,
        sip_number=config.caller_id,
        wait_until_answered=True,
        play_dialtone=True,  # the caller hears it ring
        ringing_timeout=timedelta(seconds=RING_SECONDS),
        max_call_duration=timedelta(minutes=MAX_TRANSFER_MINUTES),
        trunk=SIPOutboundConfig(
            hostname=config.address,
            auth_username=config.username,
            auth_password=config.password,
        ),
    )


async def dial(lkapi: Any, config: Config, room: str) -> str:
    """Ring the representative into the room. Returns "connected" or "no_answer"."""
    try:
        await lkapi.sip.create_sip_participant(
            dial_request(config, room), timeout=RING_SECONDS + 15
        )
        return "connected"
    except Exception as err:  # not answered, busy, rejected, trunk error
        logger.info("transfer not connected: %s", err)
        return "no_answer"
