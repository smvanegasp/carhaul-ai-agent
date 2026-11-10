"""Calls: the list and each call's record (stage 6, the "Past calls" view), and feedback per
call (stage 5).

The list and records are public on purpose (portfolio: anyone can see how Mia handled each
call). They hold the transcript, tool calls and stats the worker saved (agent/src/mia/
records.py), never phone numbers or keys. Reads are rate limited per IP.

Feedback is open to anyone who had the call (the room name is only in their browser), so it is
rate limited like fit's. It can arrive before the worker has saved the call record (the
browser shows the form the moment the call ends), so it doesn't require the record to exist.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app import db, ratelimit

router = APIRouter(prefix="/api/calls", tags=["calls"])

ROOM = re.compile(r"^(call|smoke)-[0-9a-f]{8,12}$")  # /api/token and mia.smoke room names
READS_PER_IP_PER_HOUR = 600  # the page loads the list, then one record per click
MAX_LIST = 100
FEEDBACK_PER_IP_PER_HOUR = 20
FEEDBACK_PER_DAY = 300


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)
    # The teammate tests from persona cards (docs/TESTING_GUIDE.md); optional for anyone else.
    persona: str = Field(default="", max_length=100)


class Feedback(FeedbackIn):
    id: str
    room: str
    created_at: str


@router.post("/{room}/feedback", status_code=status.HTTP_201_CREATED)
def send_feedback(room: str, body: FeedbackIn, request: Request) -> Feedback:
    if not ROOM.match(room):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such call")
    if (
        ratelimit.hit(f"feedback-ip#{ratelimit.client_ip(request)}", 3600)
        > FEEDBACK_PER_IP_PER_HOUR
        or ratelimit.hit("feedback-all", 86400) > FEEDBACK_PER_DAY
    ):
        raise ratelimit.too_many("That's a lot of feedback; thank you! Try again in a bit.")
    feedback = Feedback(
        id=uuid.uuid4().hex[:12],
        room=room,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        rating=body.rating,
        comment=body.comment.strip(),
        persona=body.persona.strip(),
    )
    db.put(f"CALL#{room}", f"FEEDBACK#{feedback.created_at}#{feedback.id}", feedback.model_dump())
    return feedback


def _limit_reads(request: Request) -> None:
    if ratelimit.hit(f"reads-ip#{ratelimit.client_ip(request)}", 3600) > READS_PER_IP_PER_HOUR:
        raise ratelimit.too_many("Too many requests. Try again in a bit.")


@router.get("")
def list_calls(request: Request, limit: int = 50) -> list[dict[str, Any]]:
    """The latest calls, newest first (the summaries records.py writes under ``CALLS``)."""
    _limit_reads(request)
    return db.latest("CALLS", max(1, min(limit, MAX_LIST)))


@router.get("/{room}")
def get_call(room: str, request: Request) -> dict[str, Any]:
    """One call's full record (transcript, events, stats) and its feedback."""
    if not ROOM.match(room):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such call")
    _limit_reads(request)
    record = db.get(f"CALL#{room}", "RECORD")
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such call")
    feedback = db.query(f"CALL#{room}", "FEEDBACK#")
    return {
        **record,
        "feedback": [
            {k: f[k] for k in ("rating", "comment", "persona", "created_at") if k in f}
            for f in feedback
        ],
    }
