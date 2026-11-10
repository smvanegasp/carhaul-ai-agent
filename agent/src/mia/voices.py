"""The voices a caller can pick for Mia: two American voices from each TTS provider.

The call page offers them in a dropdown (the list comes from ``GET /api/voices``,
backend/app/voices.py, which must have the same keys and descriptions:
``tests/test_voices.py`` checks it). The chosen key travels in the agent dispatch's metadata
(``{"voice": "<key>"}``) and the worker builds that TTS for the call; an unknown or missing
key gets ``DEFAULT``, which is also the first option on the page.

History (2026-11-09): every voice first ran at speed 0.92 after callers found Mia fast; Sergio
then found them too slow, so they're back at each provider's normal pace. He also asked for
American voices only: each one here is tagged American by its provider (Cartesia's and
Deepgram's voice catalogs, ElevenLabs' premade voice list). The ElevenLabs voice in
``ELEVENLABS_VOICE_ID`` isn't used any more (its accent couldn't be confirmed). Numbers are
written out as words before any of them speaks (speech.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from livekit.plugins import cartesia, deepgram, elevenlabs

ELEVENLABS_MODEL = "eleven_flash_v2_5"  # lowest-latency ElevenLabs model; works on the free plan
CARTESIA_MODEL = "sonic-3"


@dataclass(frozen=True)
class Voice:
    key: str
    provider: str  # "elevenlabs" | "cartesia" | "deepgram"
    label: str
    voice: str  # the provider's voice ID (Deepgram: the Aura model name)
    description: str  # shown under the dropdown so callers know what they're trying


VOICES: dict[str, Voice] = {
    v.key: v
    for v in [
        Voice(
            "cartesia-skylar",
            "cartesia",
            "Cartesia · Skylar",
            "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
            "American, friendly and approachable. Made for customer care. Cartesia Sonic-3.",
        ),
        Voice(
            "cartesia-morgan",
            "cartesia",
            "Cartesia · Morgan",
            "0ee8beaa-db49-4024-940d-c7ea09b590b3",
            "American, polished and professional. Cartesia Sonic-3.",
        ),
        Voice(
            "elevenlabs-sarah",
            "elevenlabs",
            "ElevenLabs · Sarah",
            "EXAVITQu4vr4xnSDxMaL",
            "American, warm and reassuring. ElevenLabs Flash v2.5, known for natural intonation.",
        ),
        Voice(
            "elevenlabs-jessica",
            "elevenlabs",
            "ElevenLabs · Jessica",
            "cgSgspJ2msm6clMCkdW9",
            "American, young and expressive. ElevenLabs Flash v2.5.",
        ),
        Voice(
            "deepgram-thalia",
            "deepgram",
            "Deepgram · Thalia",
            "aura-2-thalia-en",
            "American, clear and energetic. Deepgram Aura-2, built for phone agents.",
        ),
        Voice(
            "deepgram-athena",
            "deepgram",
            "Deepgram · Athena",
            "aura-2-athena-en",
            "American, calm and professional. Deepgram Aura-2.",
        ),
    ]
}
DEFAULT = "cartesia-skylar"


def pick(key: str | None) -> Voice:
    return VOICES.get(key or "", VOICES[DEFAULT])


def make_tts(voice: Voice, **extra: Any) -> Any:
    """The LiveKit TTS for this voice, at the provider's normal pace. ``extra`` goes to the
    plugin (e.g. an ``http_session`` when used outside a LiveKit job, as in the comparison)."""
    if voice.provider == "elevenlabs":
        return elevenlabs.TTS(
            voice_id=voice.voice,
            model=ELEVENLABS_MODEL,
            voice_settings=elevenlabs.VoiceSettings(stability=0.5, similarity_boost=0.75),
            # The plugin reads ELEVEN_API_KEY; our .env and SSM use ELEVENLABS_API_KEY.
            api_key=os.environ["ELEVENLABS_API_KEY"],
            **extra,
        )
    if voice.provider == "cartesia":
        return cartesia.TTS(
            model=CARTESIA_MODEL,
            voice=voice.voice,
            api_key=os.environ["CARTESIA_API_KEY"],
            **extra,
        )
    if voice.provider == "deepgram":
        return deepgram.TTS(model=voice.voice, api_key=os.environ["DEEPGRAM_API_KEY"], **extra)
    raise ValueError(f"unknown TTS provider {voice.provider!r}")
