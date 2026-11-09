"""Voice smoke test: a scripted caller phones Mia through LiveKit Cloud, no browser needed.

    uv run python -m mia.main dev      # terminal 1: the worker
    uv run python -m mia.smoke         # terminal 2: the call (about 1 min, a few cents)

The caller joins a new room with the same dispatch as /api/token, speaks each line (Deepgram
Aura TTS, a different voice from Mia's) once Mia stops talking, and prints both sides of the
transcript plus the response time as heard by the caller: from the end of the caller's audio
until Mia's state turns to "speaking". It also checks the live panel's event stream
(``mia.events``): each tool call and guardrail drop is printed, with a count by type at the
end. It uses the real APIs, including one CarHauler quote.
Pass ``--lines "..." "..."`` for another script, and ``--api http://localhost:5190`` to get
the token from the running app's /api/token (the browser's path) instead of minting one here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit import api, rtc

SAMPLE_RATE = 16000
FRAME_MS = 10
SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
SILENCE = rtc.AudioFrame(bytes(SAMPLES * 2), SAMPLE_RATE, 1, SAMPLES)
CALLER_VOICE = "aura-2-arcas-en"

DEFAULT_LINES = [
    "Yeah, sure.",
    "I need to ship my car from Miami, Florida to Boston, Massachusetts.",
    "It's a 2020 Toyota Camry.",
    "Yes, that's correct.",
    "No thanks, that's all. Bye!",
]
DIM, CYAN, GREEN, RESET = "\033[2m", "\033[36m", "\033[32m", "\033[0m"


async def synthesize(text: str) -> bytes:
    """16 kHz mono 16-bit PCM of ``text`` from Deepgram Aura."""
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            "https://api.deepgram.com/v1/speak",
            params={
                "model": CALLER_VOICE,
                "encoding": "linear16",
                "sample_rate": SAMPLE_RATE,
                "container": "none",
            },
            headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"},
            json={"text": text},
        )
        r.raise_for_status()
        return r.content


def token(room: str) -> str:
    # Same grants and dispatch as backend/app/livekit_token.py.
    return (
        api.AccessToken()
        .with_identity(f"smoke-{room}")
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=os.environ.get("MIA_AGENT_NAME") or "mia-local"
                    )
                ]
            )
        )
        .with_ttl(timedelta(minutes=10))
        .to_jwt()
    )


async def token_from_api(base: str) -> tuple[str, str, str]:
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(f"{base.rstrip('/')}/api/token")
        r.raise_for_status()
        body = r.json()
    return body["server_url"], body["participant_token"], body["room_name"]


async def run(lines: list[str], api_base: str | None = None) -> int:
    clips = await asyncio.gather(*(synthesize(line) for line in lines))
    if api_base:
        url, jwt, room_name = await token_from_api(api_base)
    else:
        room_name = f"smoke-{uuid.uuid4().hex[:8]}"
        url, jwt = os.environ["LIVEKIT_URL"], token(room_name)
    room = rtc.Room()
    agent_state = {"value": "", "changed": asyncio.Event()}
    disconnected = asyncio.Event()
    t0 = time.monotonic()

    def stamp() -> str:
        return f"{DIM}{time.monotonic() - t0:6.1f}s{RESET}"

    @room.on("participant_attributes_changed")
    def _attrs(changed: dict[str, str], participant: rtc.Participant) -> None:
        if "lk.agent.state" in changed:
            agent_state["value"] = changed["lk.agent.state"]
            agent_state["changed"].set()

    @room.on("disconnected")
    def _gone(*_) -> None:
        disconnected.set()

    async def on_transcript(reader: rtc.TextStreamReader, identity: str) -> None:
        text = await reader.read_all()
        if reader.info.attributes.get("lk.transcription_final") == "true" and text.strip():
            who = "You" if identity == room.local_participant.identity else "Mia"
            color = GREEN if who == "You" else CYAN
            print(f"{stamp()} {color}{who}:{RESET} {text.strip()}")

    room.register_text_stream_handler(
        "lk.transcription", lambda r, i: asyncio.create_task(on_transcript(r, i))
    )

    events: list[dict] = []

    async def on_event(reader: rtc.TextStreamReader, _identity: str) -> None:
        event = json.loads(await reader.read_all())
        events.append(event)
        if event["type"] == "tool":
            ok = "ok" if event["ok"] else "ERROR"
            print(f"{stamp()} {DIM}tool {event['name']} {ok} {event['ms']} ms{RESET}")
        elif event["type"] == "dropped":
            print(f"{stamp()} {DIM}guardrail dropped {event['tool']}: {event['why']}{RESET}")

    room.register_text_stream_handler(
        "mia.events", lambda r, i: asyncio.create_task(on_event(r, i))
    )

    async def wait_state(*states: str, timeout: float = 30) -> str:
        deadline = time.monotonic() + timeout
        while agent_state["value"] not in states:
            agent_state["changed"].clear()
            left = deadline - time.monotonic()
            if left <= 0 or disconnected.is_set():
                raise TimeoutError(f"agent state stayed {agent_state['value']!r}")
            try:
                await asyncio.wait_for(agent_state["changed"].wait(), left)
            except TimeoutError:
                pass
        return agent_state["value"]

    await room.connect(url, jwt)
    print(f"{stamp()} joined {room_name}; waiting for Mia")
    source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=50)
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )

    # A microphone never stops sending: silence between lines, speech when it's our turn.
    speech: asyncio.Queue[bytes] = asyncio.Queue()
    spoke_until = {"t": 0.0}

    async def pump() -> None:
        while True:
            pcm = b"" if speech.empty() else speech.get_nowait()
            if not pcm:
                await source.capture_frame(SILENCE)
                continue
            for i in range(0, len(pcm), SAMPLES * 2):
                chunk = pcm[i : i + SAMPLES * 2].ljust(SAMPLES * 2, b"\0")
                await source.capture_frame(rtc.AudioFrame(chunk, SAMPLE_RATE, 1, SAMPLES))
            spoke_until["t"] = time.monotonic()

    pump_task = asyncio.create_task(pump())
    responses: list[float] = []
    try:
        await wait_state("speaking", timeout=30)  # the greeting
        for clip in clips:
            await wait_state("listening", timeout=60)
            await asyncio.sleep(0.4)  # a human pause after Mia stops
            spoke_until["t"] = 0.0
            await speech.put(clip)
            while spoke_until["t"] == 0.0:
                await asyncio.sleep(0.01)
            # Mia goes "thinking" then "speaking"; time to the first audio as heard.
            try:
                await wait_state("speaking", timeout=20)
            except TimeoutError:
                if disconnected.is_set():
                    break
                raise
            responses.append(time.monotonic() - spoke_until["t"])
            print(f"{stamp()} {DIM}response {responses[-1] * 1000:.0f} ms{RESET}")
        try:
            await asyncio.wait_for(disconnected.wait(), 25)
            print(f"{stamp()} Mia hung up (room closed)")
        except TimeoutError:
            print(f"{stamp()} still connected after the last line (Mia didn't hang up)")
    finally:
        pump_task.cancel()
        await room.disconnect()

    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    seqs = sorted(e["seq"] for e in events)
    gaps = "none missing" if seqs == list(range(len(seqs))) else f"seq gaps in {seqs}"
    print(f"\nmia.events: {len(events)} received ({gaps}): {counts}")
    if responses:
        print(
            f"\nresponse as heard: p50 {statistics.median(responses) * 1000:.0f} ms, "
            f"max {max(responses) * 1000:.0f} ms over {len(responses)} turns "
            "(includes VAD silence + turn detector + STT + LLM + TTS + network)"
        )
    return 0 if disconnected.is_set() else 1


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", nargs="+", default=DEFAULT_LINES)
    parser.add_argument("--api", help="app base URL, e.g. http://localhost:5190")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.lines, args.api)))
