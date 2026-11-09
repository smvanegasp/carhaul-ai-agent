"""The voices a caller can pick for Mia: the top two from each TTS provider.

The call page offers them in a dropdown (the list comes from ``GET /api/voices``,
backend/app/voices.py, which must have the same keys: ``tests/test_voices.py`` checks it). The
chosen key travels in the agent dispatch's metadata (``{"voice": "<key>"}``) and the worker
builds that TTS for the call; an unknown or missing key gets ``DEFAULT``.

Pace: callers found Mia too fast (2026-11-09), so every voice runs a little slower than its
provider's default where the provider has a speed setting. Numbers are written out as words
before any of them speaks (speech.py).
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


VOICES: dict[str, Voice] = {
    v.key: v
    for v in [
        # ELEVENLABS_VOICE_ID (env): the premade voice Mia has used since stage 3.
        Voice("elevenlabs-mia", "elevenlabs", "ElevenLabs · Mia (default)", ""),
        Voice("elevenlabs-jessica", "elevenlabs", "ElevenLabs · Jessica", "cgSgspJ2msm6clMCkdW9"),
        Voice(
            "cartesia-courtney",
            "cartesia",
            "Cartesia · Courtney",
            "16a4052e-1f11-47ac-95f5-9330bee062f9",
        ),
        Voice(
            "cartesia-jessica",
            "cartesia",
            "Cartesia · Jessica",
            "25d7abcb-4d6d-4aca-adce-8a1c85620c8b",
        ),
        Voice("deepgram-thalia", "deepgram", "Deepgram · Thalia", "aura-2-thalia-en"),
        Voice("deepgram-andromeda", "deepgram", "Deepgram · Andromeda", "aura-2-andromeda-en"),
    ]
}
DEFAULT = "elevenlabs-mia"


def pick(key: str | None) -> Voice:
    return VOICES.get(key or "", VOICES[DEFAULT])


def make_tts(voice: Voice, **extra: Any) -> Any:
    """The LiveKit TTS for this voice, at Mia's pace. ``extra`` goes to the plugin (e.g. an
    ``http_session`` when used outside a LiveKit job, as in the voice comparison)."""
    if voice.provider == "elevenlabs":
        return elevenlabs.TTS(
            voice_id=voice.voice or os.environ["ELEVENLABS_VOICE_ID"],
            model=ELEVENLABS_MODEL,
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.5, similarity_boost=0.75, speed=0.92
            ),
            # The plugin reads ELEVEN_API_KEY; our .env and SSM use ELEVENLABS_API_KEY.
            api_key=os.environ["ELEVENLABS_API_KEY"],
            **extra,
        )
    if voice.provider == "cartesia":
        return cartesia.TTS(
            model=CARTESIA_MODEL,
            voice=voice.voice,
            speed=0.92,
            api_key=os.environ["CARTESIA_API_KEY"],
            **extra,
        )
    if voice.provider == "deepgram":
        return deepgram.TTS(
            model=voice.voice, speed=0.92, api_key=os.environ["DEEPGRAM_API_KEY"], **extra
        )
    raise ValueError(f"unknown TTS provider {voice.provider!r}")
