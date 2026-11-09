"""The voices a caller can pick for Mia (GET /api/voices).

The keys must match agent/src/mia/voices.py, where each one maps to a provider and voice ID
(agent/tests/test_voices.py checks both lists). The chosen key goes to the worker in the agent
dispatch's metadata (livekit_token.py).
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

DEFAULT = "elevenlabs-mia"
# (key, label) in dropdown order.
VOICES = [
    ("elevenlabs-mia", "ElevenLabs · Mia (default)"),
    ("elevenlabs-jessica", "ElevenLabs · Jessica"),
    ("cartesia-courtney", "Cartesia · Courtney"),
    ("cartesia-jessica", "Cartesia · Jessica"),
    ("deepgram-thalia", "Deepgram · Thalia"),
    ("deepgram-andromeda", "Deepgram · Andromeda"),
]
KEYS = {key for key, _ in VOICES}


class VoiceOption(BaseModel):
    key: str
    label: str
    default: bool


@router.get("/api/voices")
def list_voices() -> list[VoiceOption]:
    return [VoiceOption(key=k, label=label, default=k == DEFAULT) for k, label in VOICES]
