"""The voice worker: Mia on LiveKit Cloud.

    uv run python -m mia.main dev        # local worker: joins calls from the web app
    uv run python -m mia.main console    # talk to Mia with your own mic, no browser or room
    uv run python -m mia.main start      # production (Docker / ECS)
    uv run python -m mia.smoke           # a scripted caller phones the running worker

It registers as the agent ``mia``; the backend's ``/api/token`` dispatches it into each new
call room. Pipeline: Deepgram nova-3 (STT) → Groq gpt-oss-20b (LLM, guardrails in agent.py) →
ElevenLabs flash v2.5 (TTS), with Silero VAD, LiveKit's turn detector and interruptions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    AgentServer,
    JobContext,
    JobProcess,
    cli,
    inference,
    room_io,
)
from livekit.plugins import deepgram, elevenlabs, silero

from mia import catalog, idle, records
from mia.agent import Mia, make_llm, new_session
from mia.carhauler import CarHaulerClient
from mia.events import TOPIC, CallEvents
from mia.state import QuoteSession
from mia.tools import Services
from mia.vehicles import VehicleResolver

load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # local runs; Docker passes env vars

AGENT_NAME = "mia"  # the backend dispatches this name (backend/app/livekit_token.py)
MAX_CALL_SECONDS = float(os.environ.get("MIA_MAX_CALL_SECONDS", 6 * 60))
TTS_MODEL = "eleven_flash_v2_5"  # lowest-latency ElevenLabs model; verified on the free plan
TIME_UP = (
    "We've reached the time limit for this call, so I'll have to stop here. Thanks for calling "
    "F&F, goodbye!"
)

logger = logging.getLogger("mia.worker")


# --- per-process warm-up ---------------------------------------------------------------------


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()
    # The catalog from disk when fresh (catalog calls count toward the CarHauler allowance).
    proc.userdata["catalog"] = catalog.warm()


server = AgentServer(
    setup_fnc=prewarm,
    # Each idle process loads the VAD and the catalog. A handful is plenty at this scale
    # (the default keeps 24 warm in production).
    num_idle_processes=int(os.environ.get("MIA_IDLE_PROCESSES", 2)),
    initialize_process_timeout=30,
)
# On AWS the worker runs only around calls and exits when idle (mia/idle.py).
idle.install(server)


class RoomPublisher:
    """Sends the call's events to the room (topic ``mia.events``) in order, one at a time.

    Events can happen before the worker has joined the room (the greeting starts as the
    session starts), so they wait in a queue until it's connected.
    """

    def __init__(self, room) -> None:
        self.room = room
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.task = asyncio.create_task(self._run())

    def __call__(self, event: dict) -> None:
        self.queue.put_nowait(event)

    async def _run(self) -> None:
        while True:
            event = await self.queue.get()
            while not self.room.isconnected():
                await asyncio.sleep(0.1)
            try:
                await self.room.local_participant.send_text(
                    json.dumps(event, default=str), topic=TOPIC
                )
            except Exception as err:  # the browser left; the record still has everything
                logger.debug("couldn't send %s event: %s", event.get("type"), err)

    async def close(self, timeout: float = 2.0) -> None:
        """Give the last events (the end of the call) a moment to go out."""
        try:
            async with asyncio.timeout(timeout):
                while not self.queue.empty() and self.room.isconnected():
                    await asyncio.sleep(0.05)
        except TimeoutError:
            pass
        self.task.cancel()


def _turn_detector_version() -> dict[str, str]:
    """MIA_TURN_DETECTOR=v1 (LiveKit Cloud model) or v1-mini (runs in the worker). Unset,
    LiveKit picks v1 in `dev` and v1-mini in `start`."""
    version = os.environ.get("MIA_TURN_DETECTOR")
    return {"version": version} if version else {}


# --- one call --------------------------------------------------------------------------------


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    snapshot = ctx.proc.userdata.get("catalog") or catalog.EMPTY
    client = CarHaulerClient()
    client.seed_cache(snapshot["cache"])
    services = Services(
        carhauler=client, resolver=VehicleResolver(client, model_index=snapshot["index"])
    )
    state = QuoteSession()
    publisher = RoomPublisher(ctx.room)
    events = services.events = CallEvents(sink=publisher)
    llm = make_llm()
    turn_detector = os.environ.get("MIA_TURN_DETECTOR") or "auto"
    events.config(
        stt="Deepgram nova-3",
        llm=f"Groq {llm.model}",
        tts=f"ElevenLabs {TTS_MODEL}",
        turn_detector=f"LiveKit {turn_detector}",
        max_call_s=str(int(MAX_CALL_SECONDS)),
    )

    session = new_session(
        state,
        llm=llm,
        stt=deepgram.STT(model="nova-3", language="en-US"),
        tts=elevenlabs.TTS(
            voice_id=os.environ["ELEVENLABS_VOICE_ID"],
            model=TTS_MODEL,
            # The plugin reads ELEVEN_API_KEY; our .env and SSM use ELEVENLABS_API_KEY.
            api_key=os.environ["ELEVENLABS_API_KEY"],
        ),
        vad=ctx.proc.userdata["vad"],
        turn_handling={
            # LiveKit's end-of-turn model: waits when "I want to ship my Honda from..." trails
            # off, answers fast when the sentence is complete.
            "turn_detection": inference.TurnDetector(**_turn_detector_version()),
            # The caller can talk over Mia; a cough or "mm-hm" (< 0.5 s) doesn't stop her, and
            # if a noise did stop her she resumes after 2 s of silence (LiveKit defaults).
            "interruption": {"enabled": True},
        },
    )

    # Voice-only hooks for the tools (see tools.Services).
    def say_filler(text: str):
        events.turn("assistant", text, kind="filler")
        return session.say(text, add_to_chat_ctx=False)

    services.say_filler = say_filler
    services.end_call = session.shutdown  # drains: the goodbye finishes playing first

    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        if getattr(item, "type", None) == "message" and item.role in ("user", "assistant"):
            events.turn(
                item.role,
                item.text_content or "",
                dict(item.metrics or {}),
                interrupted=bool(getattr(item, "interrupted", False)),
            )

    async def time_limit() -> None:
        await asyncio.sleep(MAX_CALL_SECONDS)
        logger.info("max call length reached (%ss)", MAX_CALL_SECONDS)
        state.ended, state.end_reason = True, "time_limit"
        try:
            session.interrupt(force=True)
        except RuntimeError:
            pass
        events.turn("assistant", TIME_UP, kind="time_limit")
        handle = session.say(TIME_UP, allow_interruptions=False)
        handle.add_done_callback(lambda _: session.shutdown())

    timer = asyncio.create_task(time_limit())

    async def on_shutdown() -> None:
        timer.cancel()
        if not state.ended:
            state.ended, state.end_reason = True, "caller"
        events.end(state.end_reason, str(state.stage))
        record = records.build(ctx.room.name, state, events)
        logger.info(
            "call ended: %s",
            json.dumps({k: v for k, v in record.items() if k != "events"}, default=str),
        )
        await publisher.close()
        await asyncio.to_thread(records.save, record)
        await client.aclose()

    ctx.add_shutdown_callback(on_shutdown)

    await session.start(
        agent=Mia(services, speak_greeting=True),
        room=ctx.room,
        # When Mia hangs up the room is deleted, which disconnects the browser too.
        room_options=room_io.RoomOptions(delete_room_on_close=True),
    )


if __name__ == "__main__":
    cli.run_app(server)
