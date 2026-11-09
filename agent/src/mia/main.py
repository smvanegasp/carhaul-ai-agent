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

from mia import catalog
from mia.agent import Mia, new_session
from mia.carhauler import CarHaulerClient
from mia.latency import CallLatency
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
    latency = CallLatency()

    session = new_session(
        state,
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
    services.say_filler = lambda text: session.say(text, add_to_chat_ctx=False)
    services.end_call = session.shutdown  # drains: the goodbye finishes playing first

    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        if getattr(item, "type", None) == "message":
            latency.on_message(item.role, item.metrics)

    async def time_limit() -> None:
        await asyncio.sleep(MAX_CALL_SECONDS)
        logger.info("max call length reached (%ss)", MAX_CALL_SECONDS)
        state.ended, state.end_reason = True, "time_limit"
        try:
            session.interrupt(force=True)
        except RuntimeError:
            pass
        handle = session.say(TIME_UP, allow_interruptions=False)
        handle.add_done_callback(lambda _: session.shutdown())

    timer = asyncio.create_task(time_limit())

    async def on_shutdown() -> None:
        timer.cancel()
        if not state.ended:
            state.ended, state.end_reason = True, "caller"
        record = {"room": ctx.room.name, **state.to_record(), "latency": latency.summary()}
        logger.info("call ended: %s", json.dumps(record, default=str))
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
