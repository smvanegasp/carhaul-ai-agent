"""Calls: feedback per call (stage 5). Stage 6 adds the call list and detail for the dashboard.

Feedback is open to anyone who had the call (the room name is only in their browser), so it is
rate limited like fit's. It can arrive before the worker has saved the call record (the
browser shows the form the moment the call ends), so it doesn't require the record to exist.
"""

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app import db, ratelimit

router = APIRouter(prefix="/api/calls", tags=["calls"])

ROOM = re.compile(r"^(call|smoke)-[0-9a-f]{8,12}$")  # /api/token and mia.smoke room names
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
