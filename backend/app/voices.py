"""The voices a caller can pick for Mia (GET /api/voices).

The keys and descriptions must match agent/src/mia/voices.py, where each key maps to a provider
and voice ID (agent/tests/test_voices.py checks both lists). The chosen key goes to the worker
in the agent dispatch's metadata (livekit_token.py). The first voice is the one the page starts
with; the page doesn't call it "default".
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# Deepgram first (2026-11-12): the Cartesia credits are spent, and a caller who keeps the
# first voice must still hear Mia.
DEFAULT = "deepgram-thalia"
# (key, label, description) in dropdown order.
VOICES = [
    (
        "deepgram-thalia",
        "Deepgram · Thalia",
        "American, clear and energetic. Deepgram Aura-2, built for phone agents.",
    ),
    (
        "deepgram-athena",
        "Deepgram · Athena",
        "American, calm and professional. Deepgram Aura-2.",
    ),
    (
        "cartesia-skylar",
        "Cartesia · Skylar",
        "American, friendly and approachable. Made for customer care. Cartesia Sonic-3.",
    ),
    (
        "cartesia-morgan",
        "Cartesia · Morgan",
        "American, polished and professional. Cartesia Sonic-3.",
    ),
    (
        "elevenlabs-sarah",
        "ElevenLabs · Sarah",
        "American, warm and reassuring. ElevenLabs Flash v2.5, known for natural intonation.",
    ),
    (
        "elevenlabs-jessica",
        "ElevenLabs · Jessica",
        "American, young and expressive. ElevenLabs Flash v2.5.",
    ),
]
KEYS = {key for key, _, _ in VOICES}


class VoiceOption(BaseModel):
    key: str
    label: str
    description: str
    default: bool


@router.get("/api/voices")
def list_voices() -> list[VoiceOption]:
    return [
        VoiceOption(key=k, label=label, description=desc, default=k == DEFAULT)
        for k, label, desc in VOICES
    ]
