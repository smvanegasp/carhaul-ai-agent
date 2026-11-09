import {
  RoomAudioRenderer,
  RoomContext,
  StartAudio,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { Room, RoomEvent } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { CallError, fetchCallToken, wakeMia } from "../lib/api";
import { addEvent, EVENTS_TOPIC, parseEvent, type MiaEvent } from "../lib/events";
import { formatClock, toTranscript, type TranscriptLine } from "../lib/transcript";
import { FeedbackForm } from "./FeedbackForm";
import { LivePanel } from "./LivePanel";
import { useWake, type Wake } from "./useWake";

/** Mia hangs up at 6 minutes (agent/src/mia/main.py); the timer shows it. */
const MAX_CALL_SECONDS = 6 * 60;

type Phase =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "in-call"; room: Room; startedAt: number }
  | { kind: "ended"; roomName: string; transcript: TranscriptLine[] }
  | { kind: "error"; message: string };

function micErrorMessage(err: unknown): string {
  const name = err instanceof Error ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Mia needs your microphone. Allow microphone access in your browser and call again.";
  }
  if (name === "NotFoundError") return "No microphone found. Plug one in and call again.";
  return "Couldn't start the call. Please try again.";
}

export function CallPage() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const lastTranscript = useRef<TranscriptLine[]>([]);
  // Mia's events (live panel); kept after the call so the caller can look back at it.
  const [events, setEvents] = useState<MiaEvent[]>([]);
  const { wake, recheck } = useWake();

  const startCall = useCallback(async () => {
    setPhase({ kind: "connecting" });
    let room: Room | undefined;
    try {
      // She may have gone back to sleep while the page sat open: then wait for her again.
      if ((await wakeMia()).state !== "ready") {
        setPhase({ kind: "idle" });
        recheck();
        return;
      }
      setEvents([]);
      lastTranscript.current = [];
      const token = await fetchCallToken();
      room = new Room({ adaptiveStream: true, dynacast: true });
      room.registerTextStreamHandler(EVENTS_TOPIC, async (reader) => {
        const event = parseEvent(await reader.readAll());
        if (event) setEvents((prev) => addEvent(prev, event));
      });
      room.once(RoomEvent.Disconnected, () =>
        setPhase({
          kind: "ended",
          roomName: token.room_name,
          transcript: lastTranscript.current,
        }),
      );
      await room.connect(token.server_url, token.participant_token);
      await room.localParticipant.setMicrophoneEnabled(true);
      await room.startAudio(); // we're inside the click, so the browser lets audio play
      setPhase({ kind: "in-call", room, startedAt: Date.now() });
    } catch (err) {
      await room?.disconnect();
      const message = err instanceof CallError ? err.message : micErrorMessage(err);
      setPhase({ kind: "error", message });
    }
  }, [recheck]);

  const ready = wake.kind === "ready";
  return (
    <main className="mx-auto flex min-h-dvh max-w-7xl flex-col gap-6 px-4 py-8 md:py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold">Call Mia</h1>
        <p className="max-w-2xl text-stone-600">
          Mia is F&amp;F's voice assistant for open car-shipping quotes. Tell her where your car is
          going from and to, and its year, make and model, and she'll give you a price. Calls last
          up to {MAX_CALL_SECONDS / 60} minutes. The panel shows what she does under the hood: every
          tool call, what's on file and how long each step takes.
        </p>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        {phase.kind === "in-call" ? (
          <RoomContext.Provider value={phase.room}>
            <RoomAudioRenderer />
            <InCall
              room={phase.room}
              startedAt={phase.startedAt}
              onTranscript={(t) => (lastTranscript.current = t)}
            />
          </RoomContext.Provider>
        ) : (
          <section className="flex min-w-0 flex-col items-start gap-4">
            <button
              type="button"
              onClick={startCall}
              disabled={phase.kind === "connecting" || !ready}
              className="rounded-full bg-emerald-600 px-8 py-4 text-lg font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-60"
            >
              {phase.kind === "connecting"
                ? "Calling…"
                : !ready
                  ? "Mia is waking up…"
                  : phase.kind === "idle"
                    ? "Call Mia"
                    : "Call again"}
            </button>
            <WakeNote wake={wake} onRetry={recheck} />
            {phase.kind === "idle" && ready && (
              <p className="text-sm text-stone-500">
                Your browser will ask for the microphone. Calls are recorded as transcripts to
                improve Mia.
              </p>
            )}
            {phase.kind === "error" && (
              <p role="alert" className="text-red-700">
                {phase.message}
              </p>
            )}
            {phase.kind === "ended" && (
              <>
                <p className="text-stone-600">Call ended. Thanks for talking to Mia!</p>
                <FeedbackForm key={phase.roomName} room={phase.roomName} />
                {phase.transcript.length > 0 && <Transcript lines={phase.transcript} />}
              </>
            )}
          </section>
        )}
        <LivePanel events={events} live={phase.kind === "in-call"} />
      </div>
    </main>
  );
}

function WakeNote({ wake, onRetry }: { wake: Wake; onRetry: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (wake.kind !== "starting") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [wake.kind]);

  if (wake.kind === "starting") {
    return (
      <p className="text-sm text-stone-600" aria-live="polite">
        Mia only runs when someone wants to call, so she takes about a minute to wake up
        {` (${Math.round((now - wake.since) / 1000)} s so far)`}. Keep this page open.
      </p>
    );
  }
  if (wake.kind === "unavailable") {
    return (
      <p role="alert" className="text-sm text-red-700">
        {wake.message}{" "}
        <button type="button" onClick={onRetry} className="underline">
          Try again
        </button>
      </p>
    );
  }
  return null;
}

const STATE_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  "pre-connect-buffering": "Connecting…",
  initializing: "Mia is joining…",
  idle: "Mia is joining…",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Mia is speaking",
  failed: "Mia couldn't join the call",
  disconnected: "Disconnected",
};

function InCall({
  room,
  startedAt,
  onTranscript,
}: {
  room: Room;
  startedAt: number;
  onTranscript: (lines: TranscriptLine[]) => void;
}) {
  const { state } = useVoiceAssistant();
  const streams = useTranscriptions();
  const lines = toTranscript(streams, room.localParticipant.identity);
  const [now, setNow] = useState(Date.now());
  const [muted, setMuted] = useState(false);

  useEffect(() => onTranscript(lines), [lines, onTranscript]);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, []);

  const toggleMute = async () => {
    await room.localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  };

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <span
            className={`size-3 rounded-full ${
              state === "speaking"
                ? "animate-pulse bg-emerald-500"
                : state === "listening"
                  ? "bg-sky-500"
                  : "bg-stone-300"
            }`}
          />
          <span className="font-medium" aria-live="polite">
            {STATE_LABEL[state] ?? state}
          </span>
          <span className="ml-auto font-mono text-sm text-stone-500 tabular-nums">
            {formatClock((now - startedAt) / 1000)} / {formatClock(MAX_CALL_SECONDS)}
          </span>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={toggleMute}
            className="rounded-full border border-stone-300 px-5 py-2 font-medium hover:bg-stone-100"
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <button
            type="button"
            onClick={() => room.disconnect()}
            className="rounded-full bg-red-600 px-5 py-2 font-medium text-white hover:bg-red-700"
          >
            Hang up
          </button>
        </div>
        <StartAudio
          label="Tap to hear Mia"
          className="rounded-full bg-amber-500 px-5 py-2 font-medium text-white"
        />
      </div>
      <Transcript lines={lines} />
    </section>
  );
}

function Transcript({ lines }: { lines: TranscriptLine[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "nearest" }), [lines.length]);
  return (
    <div className="flex max-h-[60dvh] min-h-48 w-full flex-col gap-3 overflow-y-auto rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
      {lines.length === 0 && <p className="text-sm text-stone-400">The transcript shows here.</p>}
      {lines.map((l) => (
        <div
          key={l.id}
          className={`max-w-[85%] rounded-2xl px-4 py-2 ${
            l.who === "you"
              ? "self-end bg-sky-100 text-sky-950"
              : "self-start bg-stone-100 text-stone-900"
          } ${l.final ? "" : "opacity-60"}`}
        >
          <span className="sr-only">{l.who === "you" ? "You: " : "Mia: "}</span>
          {l.text}
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}
