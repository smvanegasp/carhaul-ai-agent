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
``TRANSFERS_PER_DAY`` (10) a day, ``RING_SECONDS`` of ringing, ``MAX_TRANSFER_MINUTES`` (10) on
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

# 10 a day (Sergio, 2026-11-11: 5 was too few with two testers); MIA_TRANSFERS_PER_DAY overrides.
TRANSFERS_PER_DAY = int(os.environ.get("MIA_TRANSFERS_PER_DAY") or 10)
# Sergio's voicemail answers after about 25-29 s of ringing (calls on 2026-11-11 reached it
# twice), so the ring stops before it can: a person picks up well within 20 s. Screening
# (press 1) still catches a voicemail that answers sooner.
RING_SECONDS = 20
MAX_TRANSFER_MINUTES = 10
REPRESENTATIVE_IDENTITY = "representative"

# What Mia says (the tool's `next` asks for the first one; the rest are spoken by code).
CONNECTING = "Sure, I'll connect you with a licensed representative now. Please stay on the line."
# Sergio, 2026-11-11: if nobody takes the call, say there's no representative available and to
# call again later. After a quote that closes the call; before one, the quote goes on.
NOBODY = (
    "I'm sorry, there's no licensed representative available right now. Please call us again later."
)
NOBODY_AFTER_QUOTE = f"{NOBODY} Thanks for calling F&F, and have a nice day!"
NOBODY_BEFORE_QUOTE = f"{NOBODY} In the meantime, I can still get you a quote."

# Mia's own voice track and the background track (hold music, typing) in the room: during
# screening the caller hears the music but not what Mia tells the line (Sergio heard the
# "press 1" whisper on 2026-11-11), and the line hears Mia but not the music.
VOICE_TRACK = "roomio_audio"
BACKGROUND_TRACK = "background_audio"


def nobody_line(state: QuoteSession, next_question: str = "") -> tuple[str, bool]:
    """What Mia says when no representative took the call, and whether the call ends there
    (after a quote there's nothing left to do)."""
    if state.quote:
        return NOBODY_AFTER_QUOTE, True
    return f"{NOBODY_BEFORE_QUOTE} {next_question}".strip(), False


def own_tracks(participant: Any, name: str) -> list[str]:
    """The sids of Mia's published audio tracks with this name."""
    return [
        pub.sid
        for pub in getattr(participant, "track_publications", {}).values()
        if getattr(pub, "name", None) == name
    ]


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
    """Who is calling and why, for the representative (the caller never hears it)."""
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


# --- screening: a person, not a voicemail ---------------------------------------------------
# Sergio's call, 2026-11-11: nobody picked up, his voicemail answered at 29 s, and the SIP leg
# counts that as answered, so Mia introduced the caller to the voicemail while the caller heard
# both. Now the line that picks up must press 1 before the caller is put through; until then the
# caller and the line can't hear each other (update_subscriptions), and without a 1 Mia hangs up
# that line and tells the caller nobody was available.

ACCEPT_DIGIT = "1"
SCREEN_SECONDS = 10  # after the prompt; then once more, shorter
SCREEN_AGAIN_SECONDS = 6
PRESS_ONE = "Press 1 to take the call."
ACCEPTED = "Thank you. I'll let you two talk now. Goodbye!"


def screening_line(state: QuoteSession) -> str:
    """What the line that picks up hears first: who's calling, then how to accept."""
    intro = handoff_line(state).removesuffix(" I'll let you two talk now. Goodbye!")
    return f"{intro} {PRESS_ONE}"


async def screen(
    say: Any,
    pressed: Any,
    line: str,
    *,
    wait_s: float = SCREEN_SECONDS,
    again_s: float = SCREEN_AGAIN_SECONDS,
) -> bool:
    """Ask the line to press 1, and wait for it (twice). ``say`` speaks a line and returns once
    it has played; ``pressed`` is an asyncio.Event set when the 1 arrives (even mid-sentence).
    True: a person accepted. False: no 1 (a voicemail, or nobody)."""
    import asyncio

    for text, wait in ((line, wait_s), (PRESS_ONE, again_s)):
        if pressed.is_set():
            return True
        await say(text)
        try:
            await asyncio.wait_for(pressed.wait(), timeout=wait)
            return True
        except TimeoutError:
            continue
    return pressed.is_set()


def audio_sids(participant: Any) -> list[str]:
    """The audio tracks a participant publishes (KIND_AUDIO is 1 in livekit.rtc)."""
    from livekit import rtc

    return [
        pub.sid
        for pub in getattr(participant, "track_publications", {}).values()
        if pub.kind == rtc.TrackKind.KIND_AUDIO
    ]


async def set_hearing(
    lkapi: Any, room: str, listener: str, track_sids: list[str], hear: bool
) -> None:
    """Let ``listener`` hear those tracks, or not (server-side, whatever the client does)."""
    if not track_sids:
        return
    from livekit.protocol.room import UpdateSubscriptionsRequest

    await lkapi.room.update_subscriptions(
        UpdateSubscriptionsRequest(
            room=room, identity=listener, track_sids=track_sids, subscribe=hear
        )
    )


async def hang_up_line(lkapi: Any, room: str) -> None:
    """Drop the representative's phone leg (it went to voicemail, or nobody pressed 1)."""
    from livekit.protocol.room import RoomParticipantIdentity

    try:
        await lkapi.room.remove_participant(
            RoomParticipantIdentity(room=room, identity=REPRESENTATIVE_IDENTITY)
        )
    except Exception as err:  # already gone
        logger.info("representative leg already gone: %s", err)


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
        # The caller hears hold music instead (main.py; Sergio: fill the silence before the
        # transfer), so no ringing tone in the room.
        play_dialtone=False,
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
