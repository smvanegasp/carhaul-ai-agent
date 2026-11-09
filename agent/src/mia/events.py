"""What happens during a call, as events: for the live panel and the call record.

Every event is a dict with ``type``, ``seq`` (order) and ``t`` (seconds since the call
started). The voice worker publishes each one to the room as a text stream on the topic
``mia.events`` (``frontend/src/lib/events.ts`` reads them), and keeps them all for the call
record (``records.py``). Text chat and tests use ``CallEvents()`` with no sink: events are only
kept.

Types:

- ``config``: the pipeline (STT, LLM, TTS, turn detector), once at the start.
- ``turn``: one line of the conversation. ``role`` is ``caller`` or ``mia``; ``kind`` is
  ``said`` (normal), ``greeting`` or ``filler`` (spoken from code, not the LLM). ``metrics`` in
  ms: caller turns carry ``end_of_turn`` and ``stt``; Mia's ``llm_ttft``, ``tts_ttfb`` and
  ``e2e`` (caller's end of speech to Mia's first audio, server side). ``speaking_s`` is how
  long that person spoke; ``interrupted`` means the caller talked over Mia.
- ``tool``: a tool call: ``name``, ``args``, ``result`` (the JSON the LLM got back), ``ok``
  and ``ms``.
- ``dropped``: a tool call the guardrail dropped before it ran (``tool``, ``args``, ``why``).
- ``state``: what's on file after a tool ran (``on_file``, ``stage``, ``quote``).
- ``end``: the call ended (``end_reason``, ``stage``, ``latency`` summary).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

from mia.latency import CallLatency

logger = logging.getLogger("mia.events")

TOPIC = "mia.events"

# LiveKit MetricsReport key -> our short name (seconds become ms).
_CALLER_METRICS = {"end_of_turn_delay": "end_of_turn", "transcription_delay": "stt"}
_MIA_METRICS = {"llm_node_ttft": "llm_ttft", "tts_node_ttfb": "tts_ttfb", "e2e_latency": "e2e"}

# A tool result is a few KB; cap what one event carries so a runaway result can't bloat the
# stream or the call record (DynamoDB items max out at 400 KB).
MAX_JSON_CHARS = 8000


def _ms(seconds: Any) -> int | None:
    return round(seconds * 1000) if isinstance(seconds, int | float) and seconds >= 0 else None


def _capped(value: Any) -> Any:
    """``value`` as is, or a note plus the start of its JSON when it is too big."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_JSON_CHARS:
        return json.loads(text)  # plain JSON types (no dataclasses, enums...)
    return {"truncated": True, "start": text[:MAX_JSON_CHARS]}


class CallEvents:
    """The events of one call. ``sink`` (optional) receives each event as it happens."""

    def __init__(self, sink: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self.sink = sink
        self.started = time.time()
        self.events: list[dict[str, Any]] = []
        self.latency = CallLatency()

    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        event = {
            "type": type_,
            "seq": len(self.events),
            "t": round(time.time() - self.started, 2),
            **data,
        }
        self.events.append(event)
        if self.sink:
            try:
                self.sink(event)
            except Exception:  # the panel is nice to have; never break the call for it
                logger.exception("couldn't publish event %s", type_)
        return event

    # --- helpers for each type -----------------------------------------------------------

    def config(self, **pipeline: str) -> None:
        self.emit("config", **pipeline)

    def turn(
        self,
        role: str,
        text: str,
        metrics: dict[str, Any] | None = None,
        *,
        kind: str = "said",
        interrupted: bool = False,
    ) -> None:
        """One conversation line. ``role`` is LiveKit's: ``user`` or ``assistant``."""
        report = metrics or {}
        self.latency.on_message(role, report)
        names = _CALLER_METRICS if role == "user" else _MIA_METRICS
        ms = {short: _ms(report.get(key)) for key, short in names.items()}
        start, stop = report.get("started_speaking_at"), report.get("stopped_speaking_at")
        speaking = round(stop - start, 2) if start and stop and stop >= start else None
        self.emit(
            "turn",
            role="caller" if role == "user" else "mia",
            kind=kind,
            text=text,
            metrics={k: v for k, v in ms.items() if v is not None},
            speaking_s=speaking,
            interrupted=interrupted,
        )

    def tool(
        self, name: str, args: dict[str, Any], result: dict[str, Any] | None, ms: float
    ) -> None:
        ok = bool(result and result.get("ok", True))
        self.emit(
            "tool",
            name=name,
            args=_capped(args),
            result=_capped(result),
            ok=ok,
            ms=round(ms),
        )

    def dropped(self, tool: str, args: str, why: str) -> None:
        self.emit("dropped", tool=tool, args=args[:2000], why=why)

    def state(self, on_file: dict[str, Any], stage: str, quote: dict[str, Any] | None) -> None:
        self.emit("state", on_file=_capped(on_file), stage=stage, quote=_capped(quote))

    def end(self, end_reason: str | None, stage: str) -> None:
        self.emit("end", end_reason=end_reason, stage=stage, latency=self.latency.summary())

    # --- for the call record -------------------------------------------------------------

    def transcript(self) -> list[dict[str, Any]]:
        return [
            {"t": e["t"], "role": e["role"], "kind": e["kind"], "text": e["text"]}
            for e in self.events
            if e["type"] == "turn"
        ]

    def talk_seconds(self) -> dict[str, float]:
        """Seconds each side spoke (from LiveKit's speaking timestamps)."""
        out = {"caller": 0.0, "mia": 0.0}
        for e in self.events:
            if e["type"] == "turn" and e.get("speaking_s"):
                out[e["role"]] = round(out[e["role"]] + e["speaking_s"], 2)
        return out
