"""Noisy places: classrooms, the subway, a crowd (Belinda's demo, 2026-11-12).

Observed: in a classroom with other people talking, Mia didn't talk. Background voices are
speech to every part of the pipeline, so:

- the caller's turn never ended (the voice detector never heard silence), so Mia never
  answered;
- when she did speak, any word from the room interrupted her (``min_words`` 1 from 2026-11-11
  stops noise, not voices).

Three layers, in order:

1. **Background voice cancellation** (LiveKit Cloud's Krisp BVC, ``noise_filter``) on the
   caller's audio before the voice detector, STT and turn detector hear it: it keeps the main
   speaker and removes other voices and noise. A phone line (SIP) gets the telephony model.
2. **A turn can't last forever** (``TURN_LIMIT_S``): if the caller has been "speaking" that
   long without Mia answering, ``Mia.on_user_turn_exceeded`` ends the turn and she answers what
   she heard, with tools and guardrails as usual (LiveKit's default replies with no tools).
   25 s normally: real callers giving two cars in one breath talk up to 24 s (48 calls, 263
   turns, 2026-11-12: 9.9% of turns were 12 s or more, the longest 23.9 s), and those are the
   turns worth hearing out. Belinda: don't cut off someone who's really talking.
3. **Noisy-call mode** (``NoiseWatch``): after ``SIGNALS_FOR_NOISY`` signs of noise (Mia cut
   off, a turn that hit the limit), interrupting her takes ``NOISY_MIN_WORDS`` words instead
   of one and the turn limit drops to ``NOISY_TURN_LIMIT_S``, for the rest of the call; she
   says once that it's noisy (``NOISY_LINE``, before her next answer).

Which layers are on is the call's *profile* (``PROFILES``): ``full`` (all three, the default),
``filter`` (1 only) or ``baseline`` (none: how Mia was before). ``MIA_NOISE_HANDLING`` sets it
for the worker; a scripted test call can ask for one in its dispatch metadata (``noise``), so
``evals/noisy_calls.py`` compares them against one running worker. The browser's token never
carries it.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

from livekit import rtc

# Imported at load, in the worker's main process, as LiveKit's docs do: importing the plugin
# loads its native library.
from livekit.plugins import noise_cancellation

from mia.state import QuoteSession

logger = logging.getLogger("mia.noise")

# Longer than any real caller turn seen (23.9 s); a classroom never stops, so once the call is
# known to be noisy the limit is shorter.
TURN_LIMIT_S = 25.0
NOISY_TURN_LIMIT_S = 12.0
SIGNALS_FOR_NOISY = 3
NORMAL_MIN_WORDS = 1
NOISY_MIN_WORDS = 3
NOISY_LINE = "It sounds a bit noisy where you are, so I'll keep talking unless you stop me."


PROFILES = ("full", "filter", "baseline")


def profile(requested: object = None) -> str:
    """The call's profile: the one ``requested`` (dispatch metadata) if valid, else
    ``MIA_NOISE_HANDLING``, else ``full``."""
    for value in (requested, os.environ.get("MIA_NOISE_HANDLING")):
        if isinstance(value, str) and value.strip().lower() in PROFILES:
            return value.strip().lower()
    return "full"


def noise_filter(profile: str):
    """The caller's audio filter for ``room_io.AudioInputOptions(noise_cancellation=...)``:
    BVC for a browser caller, BVCTelephony for a phone line; None for ``baseline``. A
    selector, so the right model is picked per participant.

    Not on Windows: there the filter crashes the worker (2026-11-12, livekit 1.8.11 /
    rtc 1.2.0: "Assertion failed! FFT_LEN == -1" in livekit_ffi.dll's soxr resampler as the
    caller's audio opens). AWS and Docker run Linux, where it works; a worker on Sergio's
    Windows machine keeps the other two layers."""
    if profile == "baseline":
        return None
    if sys.platform == "win32":
        logger.warning("background voice cancellation is off on Windows (it crashes there)")
        return None

    def pick(params):
        if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            return noise_cancellation.BVCTelephony()
        return noise_cancellation.BVC()

    return pick


def turn_limit(profile: str) -> dict[str, Any]:
    """``turn_handling["user_turn_limit"]`` for the profile (empty: no limit)."""
    return {"max_duration": TURN_LIMIT_S} if profile == "full" else {}


@dataclass
class NoiseWatch:
    """Counts signs of a noisy call and decides when to switch to noisy-call mode."""

    signals: int = 0
    noisy: bool = False

    def signal(self, state: QuoteSession, why: str) -> bool:
        """One sign of noise (``why``: "interrupted", "long_turn"). True when this one switches
        the call to noisy mode (only once per call)."""
        self.signals += 1
        state.noise_signals = self.signals
        if self.noisy or self.signals < SIGNALS_FOR_NOISY:
            return False
        self.noisy = state.noisy = True
        state.noisy_line_due = True
        logger.info("noisy call after %d signals (last: %s)", self.signals, why)
        return True


def with_noisy_line(spoken: str, state: QuoteSession) -> str:
    """Mia's next answer after the switch starts with ``NOISY_LINE`` (once)."""
    if not spoken or not state.noisy_line_due:
        return spoken
    state.noisy_line_due = False
    return f"{NOISY_LINE} {spoken}"


def go_noisy(turn_handling: dict[str, Any]) -> None:
    """Noisy-call mode in the session's live options (``session.options.turn_handling``):
    LiveKit reads ``interruption`` on every interruption check and ``user_turn_limit`` on every
    final transcript, so changing them mid-call takes effect at once (livekit-agents 1.8.11,
    agent_activity.py and audio_recognition.py)."""
    turn_handling["interruption"]["min_words"] = NOISY_MIN_WORDS
    limit = turn_handling.get("user_turn_limit")
    if limit is not None and limit.get("max_duration") is not None:
        limit["max_duration"] = NOISY_TURN_LIMIT_S
