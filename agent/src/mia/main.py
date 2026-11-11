"""The voice worker: Mia on LiveKit Cloud.

    uv run python -m mia.main dev        # local worker: joins calls from the web app
    uv run python -m mia.main console    # talk to Mia with your own mic, no browser or room
    uv run python -m mia.main start      # production (Docker / ECS)
    uv run python -m mia.smoke           # a scripted caller phones the running worker

It registers as ``MIA_AGENT_NAME`` (``mia`` on AWS, ``mia-local`` anywhere else); the
backend's ``/api/token`` dispatches that name into each new
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
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    JobContext,
    JobProcess,
    cli,
    inference,
    room_io,
)
from livekit.plugins import deepgram, silero

from mia import catalog, guardrails, idle, records, silence, transfer, voices
from mia.agent import Mia, make_llm, new_session
from mia.carhauler import CarHaulerClient
from mia.events import TOPIC, CallEvents
from mia.state import QuoteSession
from mia.tools import Services
from mia.vehicles import VehicleResolver

load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # local runs; Docker passes env vars

# The name the backend dispatches into each call room (backend/app/livekit_token.py). Only AWS
# uses "mia"; anything local defaults to "mia-local", so a worker on a laptop can't take calls
# from the live site (both share one LiveKit project; seen on 2026-11-09).
AGENT_NAME = os.environ.get("MIA_AGENT_NAME") or "mia-local"
MAX_CALL_SECONDS = float(os.environ.get("MIA_MAX_CALL_SECONDS", 6 * 60))
# Keyboard typing between "give me one second" and the price, so it feels calculated.
TYPING_SECONDS = 2.0
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


def _dispatch_metadata(ctx: JobContext) -> dict:
    """What the API put in the agent dispatch (backend/app/livekit_token.py): the caller's
    voice choice. Anything unreadable means defaults."""
    try:
        data = json.loads(ctx.job.metadata or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


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
    voice = voices.pick(_dispatch_metadata(ctx).get("voice"))
    turn_detector = os.environ.get("MIA_TURN_DETECTOR") or "auto"
    events.config(
        stt="Deepgram nova-3",
        llm=f"Groq {llm.model}",
        tts=voice.label,
        turn_detector=f"LiveKit {turn_detector}",
        max_call_s=str(int(MAX_CALL_SECONDS)),
    )

    session = new_session(
        state,
        llm=llm,
        stt=deepgram.STT(model="nova-3", language="en-US"),
        tts=voices.make_tts(voice),
        vad=ctx.proc.userdata["vad"],
        turn_handling={
            # LiveKit's end-of-turn model: waits when "I want to ship my Honda from..." trails
            # off, answers fast when the sentence is complete.
            "turn_detection": inference.TurnDetector(**_turn_detector_version()),
            # The caller can talk over Mia, but a sound isn't a voice (Belinda, 2026-11-11: a
            # little background noise stopped her). With plain voice-activity detection any
            # 0.5 s of sound interrupted her; now speech-to-text must also have heard at least
            # one word (noise has none). If something still stops her, she resumes after 2 s
            # of silence. LiveKit's "adaptive" detector (MIA_INTERRUPTION=adaptive) is opt-in:
            # in a local test call (2026-11-11) the worker process died silently as it started.
            "interruption": {
                "enabled": True,
                "mode": os.environ.get("MIA_INTERRUPTION") or "vad",
                "min_words": 1,
            },
        },
    )

    # Voice-only hooks for the tools (see tools.Services).
    background = BackgroundAudioPlayer()

    def before_quote(text: str) -> asyncio.Future[None]:
        """Filler line, then ~2 s of keyboard typing on its own track; the future is done when
        Mia may read the price (tools.get_quote waits for it)."""
        events.turn("assistant", text, kind="filler")
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def typing() -> None:
            try:
                play = background.play(AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8))
                await asyncio.sleep(TYPING_SECONDS)
                play.stop()
            except Exception:  # the sound is a nicety; never block the quote on it
                logger.warning("typing sound failed", exc_info=True)
            finally:
                if not done.done():
                    done.set_result(None)

        handle = session.say(text, add_to_chat_ctx=False)
        handle.add_done_callback(lambda _: asyncio.ensure_future(typing()))
        return done

    services.before_quote = before_quote
    services.end_call = session.shutdown  # drains: the goodbye finishes playing first

    # Phone transfer to a licensed representative (transfer.py), when the trunk is configured.
    phone_line = transfer.Config.from_env()

    async def hear_each_other(hear: bool) -> None:
        """Caller <-> representative audio, on or off (off while the line is screened)."""
        rep = ctx.room.remote_participants.get(transfer.REPRESENTATIVE_IDENTITY)
        for _ in range(20):  # its track publishes a moment after the answer
            if rep and transfer.audio_sids(rep):
                break
            await asyncio.sleep(0.1)
            rep = ctx.room.remote_participants.get(transfer.REPRESENTATIVE_IDENTITY)
        rep_sids = transfer.audio_sids(rep) if rep else []
        room = ctx.room.name
        for p in list(ctx.room.remote_participants.values()):
            if p.identity == transfer.REPRESENTATIVE_IDENTITY:
                continue
            try:
                await transfer.set_hearing(ctx.api, room, p.identity, rep_sids, hear)
                await transfer.set_hearing(
                    ctx.api, room, transfer.REPRESENTATIVE_IDENTITY, transfer.audio_sids(p), hear
                )
            except Exception as err:  # never break the transfer over routing
                logger.warning(
                    "couldn't %s audio for %s: %s", "route" if hear else "hold", p.identity, err
                )

    async def route_mia(screening: bool) -> None:
        """While the line is screened the caller hears the hold music but not Mia's whisper to
        the line, and the line hears Mia but not the music; afterwards, back to normal."""
        me, room = ctx.room.local_participant, ctx.room.name
        voice = transfer.own_tracks(me, transfer.VOICE_TRACK)
        music = transfer.own_tracks(me, transfer.BACKGROUND_TRACK)
        for p in list(ctx.room.remote_participants.values()):
            hide = voice if p.identity != transfer.REPRESENTATIVE_IDENTITY else music
            try:
                await transfer.set_hearing(ctx.api, room, p.identity, hide, not screening)
            except Exception as err:  # never break the transfer over routing
                logger.warning("couldn't route Mia's audio for %s: %s", p.identity, err)

    told_line: list[str] = []  # what Mia said to the line while screening (not to the caller)

    async def screen_line() -> bool:
        """The line that picked up must press 1 (transfer.screen); the caller and the line
        can't hear each other until then. What Mia tells the line isn't a turn of the call:
        the caller doesn't hear it, so it's not transcribed either (Belinda, 2026-11-11: the
        "Press 1" lines showed up in her chat). It goes in screen_representative's event."""
        await hear_each_other(False)
        await route_mia(screening=True)
        session.output.set_transcription_enabled(False)
        pressed = asyncio.Event()

        def on_dtmf(ev) -> None:
            who = getattr(ev.participant, "identity", None)
            if who == transfer.REPRESENTATIVE_IDENTITY and ev.digit == transfer.ACCEPT_DIGIT:
                pressed.set()

        async def say(text: str) -> None:
            told_line.append(text)
            handle = session.say(text, allow_interruptions=False, add_to_chat_ctx=False)
            await handle.wait_for_playout()

        ctx.room.on("sip_dtmf_received", on_dtmf)
        try:
            accepted = await transfer.screen(say, pressed, transfer.screening_line(state))
            if accepted:
                # Still screened: only the representative hears it (Belinda, 2026-11-11, call
                # fde275e6bce5: the caller heard and saw "I'll let you two talk now").
                await say(transfer.ACCEPTED)
        finally:
            ctx.room.off("sip_dtmf_received", on_dtmf)
            stop_music()
            session.output.set_transcription_enabled(True)
            await route_mia(screening=False)
        if accepted:
            await hear_each_other(True)
        logger.info("representative line %s", "accepted" if accepted else "not accepted")
        return accepted

    hold = {"music": None}

    def start_music() -> None:
        """Hold music while the line rings and is screened (Sergio, 2026-11-11: fill the
        silence before the transfer). A nicety: never blocks the transfer."""
        try:
            hold["music"] = background.play(
                AudioConfig(BuiltinAudioClip.HOLD_MUSIC, volume=0.5), loop=True
            )
        except Exception:
            logger.warning("hold music failed", exc_info=True)

    def stop_music() -> None:
        music, hold["music"] = hold["music"], None
        if music is not None:
            try:
                music.stop()
            except Exception:
                logger.debug("hold music already stopped", exc_info=True)

    async def run_transfer() -> None:
        """Ring the representative into this room; on answer Mia introduces the caller and
        leaves, otherwise she apologizes (and closes the call if it was quoted)."""
        session.input.set_audio_enabled(False)  # nobody to answer while it rings
        started = asyncio.get_running_loop().time()
        outcome = "limit"
        if await asyncio.to_thread(transfer.take_slot):
            start_music()
            outcome = await transfer.dial(ctx.api, phone_line, ctx.room.name)
            if outcome != "connected":
                stop_music()
        # "screening" until the line presses 1 (transfer.screen): a voicemail also "answers".
        state.transfer = "screening" if outcome == "connected" else outcome
        events.tool(
            "dial_representative",
            {},
            {"ok": outcome == "connected", "outcome": outcome},
            (asyncio.get_running_loop().time() - started) * 1000,
        )
        events.state(state.snapshot(), str(state.stage), state.quote)
        try:
            if outcome == "connected":
                screened = asyncio.get_running_loop().time()
                accepted = await screen_line()
                if not accepted:
                    await transfer.hang_up_line(ctx.api, ctx.room.name)
                    outcome = "no_answer"
                state.transfer = "connected" if accepted else outcome
                events.tool(
                    "screen_representative",
                    {},
                    {
                        "ok": accepted,
                        "outcome": "accepted" if accepted else "no 1 pressed",
                        "told_line": told_line,
                    },
                    (asyncio.get_running_loop().time() - screened) * 1000,
                )
                events.state(state.snapshot(), str(state.stage), state.quote)
            if outcome == "connected":
                timer.cancel()  # Mia's 6-minute limit; the phone leg has its own (10 min)
                # She already told the line goodbye while screening; now she just leaves.
                session.shutdown()
                asyncio.get_running_loop().call_later(
                    transfer.MAX_TRANSFER_MINUTES * 60 + 60, lambda: ctx.delete_room()
                )
            else:
                session.input.set_audio_enabled(True)
                line, closes = transfer.nobody_line(state, guardrails.fallback_line(state))
                events.turn("assistant", line, kind="transfer_failed")
                if closes:
                    state.ended, state.end_reason = True, "mia"
                handle = session.say(line, allow_interruptions=not closes)
                if closes:
                    handle.add_done_callback(lambda _: session.shutdown())
        except RuntimeError:  # the caller hung up while it rang; the session is gone
            logger.info("transfer finished after the session closed (%s)", outcome)
        finally:
            stop_music()

    if phone_line:
        services.transfer = lambda: asyncio.ensure_future(run_transfer())

    @session.on("close")
    def _on_close(_ev) -> None:
        # The room ends with Mia's session, except after a transfer: then the caller and the
        # representative keep talking, and it ends when either hangs up.
        if state.transfer != "connected":
            ctx.delete_room()

    @ctx.room.on("participant_disconnected")
    def _on_left(participant) -> None:
        if state.transfer == "connected":
            logger.info("%s left the transferred call; closing the room", participant.identity)
            ctx.delete_room()

    @session.on("agent_state_changed")
    def _on_state(ev) -> None:
        # Mia said goodbye without end_call (agent.llm_node): hang up once it has played.
        if state.hang_up_after_speech and ev.new_state == "listening":
            state.hang_up_after_speech = False
            session.shutdown()

    # The caller went quiet (silence.py): ask if they're there, or say goodbye and hang up.
    away = {"prompts": 0}

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        if ev.new_state == "speaking":
            away["prompts"] = 0
            return
        if ev.new_state != "away":
            return
        action = silence.on_away(state, away["prompts"])
        if action is None:
            return
        line, hang_up = action
        away["prompts"] += 1
        logger.info("caller silent; %s", "hanging up" if hang_up else "checking in")
        events.turn("assistant", line, kind="silence")
        if hang_up:
            state.ended, state.end_reason = True, "silence"
        handle = session.say(line, allow_interruptions=not hang_up)
        if hang_up:
            handle.add_done_callback(lambda _: session.shutdown())
        else:
            # The caller stays "away" until they speak, so LiveKit wouldn't count a second
            # silence: back to "listening" once the line has played restarts the countdown
            # (seen in the first live test, 2026-11-10: no goodbye after "are you still there?").
            handle.add_done_callback(lambda _: session.reset_away_timer())

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
        # The room is deleted when Mia's session closes (_on_close above), which disconnects the
        # browser too; after a transfer only when the caller or representative hangs up.
        room_options=room_io.RoomOptions(delete_room_on_close=False),
    )
    await background.start(room=ctx.room, agent_session=session)


if __name__ == "__main__":
    cli.run_app(server)
