"""Latency of one voice call, per component and end to end.

LiveKit attaches a metrics report to every message added to the conversation
(``conversation_item_added`` → ``ChatMessage.metrics``; the older ``metrics_collected`` event
is deprecated in 1.8):

- caller messages: ``end_of_turn_delay`` (from the end of their speech until the turn is
  committed: VAD silence + turn detector) and ``transcription_delay`` (STT)
- Mia's messages: ``llm_node_ttft`` (LLM time to first token, after our guardrail),
  ``tts_node_ttfb`` (TTS time to first audio) and ``e2e_latency`` (from the end of the
  caller's speech until Mia starts answering, including tool time)

``e2e_latency`` excludes the network to the browser. Measured on 2026-11-09 with
``python -m mia.smoke`` (5 turns): server-side e2e p50 734 ms vs 1.39 s heard by the caller,
the gap being the VAD's 0.55 s of silence before it decides speech ended, plus the network.

The worker logs ``summary()`` when the call ends; stage 5 sends the per-turn values to the
live panel and the call record.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# Caller-side and Mia-side keys of livekit.agents.llm.MetricsReport we keep.
USER_KEYS = ("end_of_turn_delay", "transcription_delay")
AGENT_KEYS = ("e2e_latency", "llm_node_ttft", "tts_node_ttfb")


def _stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    p90 = ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]
    return {
        "n": len(values),
        "p50_ms": round(statistics.median(values) * 1000),
        "p90_ms": round(p90 * 1000),
        "mean_ms": round(statistics.fmean(values) * 1000),
    }


@dataclass
class CallLatency:
    values: dict[str, list[float]] = field(
        default_factory=lambda: {k: [] for k in USER_KEYS + AGENT_KEYS}
    )

    def on_message(self, role: str, report: dict[str, Any] | None) -> None:
        """One conversation message (``ChatMessage.role`` and ``.metrics``)."""
        keys = USER_KEYS if role == "user" else AGENT_KEYS if role == "assistant" else ()
        for key in keys:
            value = (report or {}).get(key)
            if isinstance(value, int | float) and value >= 0:
                self.values[key].append(float(value))

    def summary(self) -> dict[str, dict[str, float] | None]:
        return {key: _stats(vals) for key, vals in self.values.items()}
