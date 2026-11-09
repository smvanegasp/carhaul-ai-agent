"""POST /api/token: a LiveKit access token for one browser call with Mia.

Each call gets its own room (``call-<id>``). The token carries a room configuration that
dispatches the ``mia`` agent worker into the room as soon as the caller joins (explicit
dispatch: the worker never joins rooms on its own).

Every call spends money (Deepgram, Groq, ElevenLabs, LiveKit), so calls are rate limited per
IP and per day, and the token and room are short-lived. Mia herself hangs up at the max call
length (agent/src/mia/main.py).
"""

import os
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from livekit import api
from pydantic import BaseModel

from app import ratelimit

AGENT_NAME = "mia"  # agent/src/mia/main.py registers this name

router = APIRouter()


def _limit(name: str, default: int) -> int:
    return int(os.environ.get(name) or default)


class CallToken(BaseModel):
    # Field names follow LiveKit's standard token endpoint, so the web SDK can use it directly.
    server_url: str
    participant_token: str
    room_name: str


@router.post("/api/token")
def create_call_token(request: Request) -> CallToken:
    url, key, secret = (
        os.environ.get("LIVEKIT_URL"),
        os.environ.get("LIVEKIT_API_KEY"),
        os.environ.get("LIVEKIT_API_SECRET"),
    )
    if not (url and key and secret):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Calling isn't set up yet")

    # Like fit: the daily counter only counts calls that passed the per-IP limit, so one
    # caller hammering the button can't use up everyone's calls for the day.
    if ratelimit.hit(f"call-ip#{ratelimit.client_ip(request)}", 3600) > _limit(
        "CALLS_PER_IP_PER_HOUR", 6
    ):
        raise ratelimit.too_many("That's a lot of calls in a short time. Try again in a bit.")
    if ratelimit.hit("call-all", 86400) > _limit("CALLS_PER_DAY", 60):
        raise ratelimit.too_many("Mia has taken all the calls she can for today. Try tomorrow!")

    call_id = uuid.uuid4().hex[:12]
    room = f"call-{call_id}"
    token = (
        api.AccessToken(key, secret)
        .with_identity(f"caller-{call_id}")
        .with_name("Caller")
        # Long enough to join; the call itself is capped by the agent (6 min).
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_publish_sources=["microphone"],
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)],
                max_participants=2,  # the caller and Mia
                empty_timeout=60,
                departure_timeout=10,
            )
        )
    )
    return CallToken(server_url=url, participant_token=token.to_jwt(), room_name=room)
