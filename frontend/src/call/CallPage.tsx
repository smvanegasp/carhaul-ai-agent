import {
  RoomAudioRenderer,
  RoomContext,
  StartAudio,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { Room, RoomEvent } from "livekit-client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { CallError, fetchCallToken, wakeMia } from "../lib/api";
import { buildConversation } from "../lib/conversation";
import { addEvent, EVENTS_TOPIC, parseEvent, type MiaEvent } from "../lib/events";
import { formatClock, toTranscript, type TranscriptLine } from "../lib/transcript";
import { Conversation } from "./Conversation";
import { ErrorBoundary } from "./ErrorBoundary";
import { FeedbackForm } from "./FeedbackForm";
import { Insights } from "./Insights";
import { wakeProgress } from "../lib/wake";
import { ThemeToggle } from "./ThemeToggle";
import { useWake, type Wake } from "./useWake";
import { useVoiceChoice, VoicePicker } from "./VoicePicker";

/** Mia hangs up at 6 minutes (agent/src/mia/main.py); the timer shows it. */
const MAX_CALL_SECONDS = 6 * 60;

type Phase =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "in-call"; room: Room; startedAt: number }
  | { kind: "ended"; roomName: string; lines: TranscriptLine[] }
  | { kind: "error"; message: string };

function micErrorMessage(err: unknown): string {
  const name = err instanceof Error ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Mia needs your microphone. Allow microphone access in your browser and call again.";
  }
  if (name === "NotFoundError") return "No microphone found. Plug one in and call again.";
  return "Couldn't start the call. Please try again.";
}

/**
 * Layout: on desktop the page fits the screen; the side column holds the call controls and
 * the stats, and the conversation is the only part that scrolls. On a phone everything flows
 * in one column (controls, conversation, stats) and the page scrolls as a whole.
 */
export function CallPage() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const lastLines = useRef<TranscriptLine[]>([]);
  // Mia's events; kept after the call so the caller can look back at it.
  const [events, setEvents] = useState<MiaEvent[]>([]);
  const { wake, recheck } = useWake();
  const [details, setDetails] = useState(false);
  const voices = useVoiceChoice();

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
      lastLines.current = [];
      const token = await fetchCallToken(fetch, voices.selected ?? undefined);
      room = new Room({ adaptiveStream: true, dynacast: true });
      room.registerTextStreamHandler(EVENTS_TOPIC, async (reader) => {
        const event = parseEvent(await reader.readAll());
        if (event) setEvents((prev) => addEvent(prev, event));
      });
      room.once(RoomEvent.Disconnected, () =>
        setPhase({ kind: "ended", roomName: token.room_name, lines: lastLines.current }),
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
  }, [recheck, voices.selected]);

  const inCall = phase.kind === "in-call";
  const callCard = inCall ? (
    <ErrorBoundary fallback={<InCallFallback room={phase.room} />}>
      <InCallControls room={phase.room} startedAt={phase.startedAt} />
    </ErrorBoundary>
  ) : (
    <CallButtonCard
      phase={phase}
      wake={wake}
      onCall={startCall}
      onRetry={recheck}
      voicePicker={
        <VoicePicker
          options={voices.options}
          selected={voices.selected}
          onChoose={voices.choose}
          disabled={phase.kind === "connecting"}
        />
      }
    />
  );
  const conversation = inCall ? (
    <LiveConversation
      room={phase.room}
      events={events}
      details={details}
      onDetails={setDetails}
      onLines={(lines) => {
        lastLines.current = lines;
      }}
    />
  ) : (
    <Conversation
      items={buildConversation(phase.kind === "ended" ? phase.lines : [], events)}
      live={false}
      details={details}
      onDetails={setDetails}
      footer={
        phase.kind === "ended" ? (
          <FeedbackForm key={phase.roomName} room={phase.roomName} />
        ) : undefined
      }
    />
  );

  const page = (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 lg:h-dvh lg:overflow-hidden lg:py-6">
      <header className="flex flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          <h1 className="font-display text-3xl tracking-tight">
            Call Mia <span className="text-muted">· F&amp;F car shipping quotes</span>
          </h1>
          <ThemeToggle />
        </div>
        <p className="max-w-3xl text-sm text-muted">
          Mia is a voice assistant for open car-shipping quotes. Tell her where your car is going
          from and to, and its year, make and model. Calls last up to {MAX_CALL_SECONDS / 60}{" "}
          minutes.
        </p>
      </header>

      <div className="flex flex-col gap-4 lg:grid lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(300px,380px)_1fr] lg:grid-rows-[auto_1fr]">
        <div className="lg:col-start-1 lg:row-start-1">{callCard}</div>
        <div className="flex flex-col lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:min-h-0">
          <ErrorBoundary fallback={<Notice>The conversation view hit a display error.</Notice>}>
            {conversation}
          </ErrorBoundary>
        </div>
        <div className="lg:col-start-1 lg:row-start-2 lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain">
          <ErrorBoundary fallback={<Notice>The stats hit a display error.</Notice>}>
            <Insights events={events} />
          </ErrorBoundary>
        </div>
      </div>
    </main>
  );

  return inCall ? (
    <RoomContext.Provider value={phase.room}>
      <RoomAudioRenderer />
      {page}
    </RoomContext.Provider>
  ) : (
    page
  );
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-2xl border border-line bg-surface p-4 text-sm text-muted">{children}</p>
  );
}

function CallButtonCard({
  phase,
  wake,
  onCall,
  onRetry,
  voicePicker,
}: {
  phase: Phase;
  wake: Wake;
  onCall: () => void;
  onRetry: () => void;
  voicePicker: ReactNode;
}) {
  const ready = wake.kind === "ready";
  return (
    <section className="flex flex-col items-start gap-3 rounded-2xl border border-line bg-surface p-4">
      {voicePicker}
      <button
        type="button"
        onClick={onCall}
        disabled={phase.kind === "connecting" || !ready}
        className="w-full rounded-full bg-brand px-8 py-3.5 text-lg font-semibold text-brand-ink shadow-sm transition hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none disabled:cursor-wait disabled:opacity-60"
      >
        {phase.kind === "connecting"
          ? "Calling…"
          : !ready
            ? "Mia is waking up…"
            : phase.kind === "ended"
              ? "Call again"
              : "Call Mia"}
      </button>
      <WakeNote wake={wake} onRetry={onRetry} />
      {phase.kind === "error" && (
        <p role="alert" className="text-sm text-danger">
          {phase.message}
        </p>
      )}
      {phase.kind === "ended" && (
        <p className="text-sm text-muted">
          Call ended. Thanks for talking to Mia! Scroll the conversation to look back at it.
        </p>
      )}
      {phase.kind === "idle" && ready && (
        <p className="text-sm text-muted">
          Your browser will ask for the microphone. Headphones work best. Calls are kept as
          transcripts to improve Mia.
        </p>
      )}
    </section>
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
    const elapsed = now - wake.since;
    const { percent, label } = wakeProgress(elapsed, wake.step);
    return (
      <div className="flex flex-col gap-2 text-sm">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-medium text-ink" aria-live="polite">
            {label}…
          </span>
          <span className="font-mono text-xs text-muted tabular-nums">
            {Math.round(elapsed / 1000)} s
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Waking Mia up"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="h-2 overflow-hidden rounded-full bg-raised"
        >
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-linear"
            style={{ width: `${percent}%` }}
          />
        </div>
        <p className="text-muted">
          Mia only runs when someone wants to call, so she takes about a minute to wake up. Keep
          this page open.
        </p>
      </div>
    );
  }
  if (wake.kind === "unavailable") {
    return (
      <p role="alert" className="text-sm text-danger">
        {wake.message}{" "}
        <button type="button" onClick={onRetry} className="underline">
          Try again
        </button>
      </p>
    );
  }
  return null;
}

/** Shown if the call controls break: the call (and Mia's audio) keeps going. */
function InCallFallback({ room }: { room: Room }) {
  return (
    <section className="flex flex-col items-start gap-3 rounded-2xl border border-line bg-surface p-4">
      <p className="text-sm">You're still on the call with Mia; this view hit a display error.</p>
      <HangUp room={room} />
    </section>
  );
}

function HangUp({ room }: { room: Room }) {
  return (
    <button
      type="button"
      onClick={() => room.disconnect()}
      className="rounded-full bg-danger px-5 py-2 font-medium text-surface hover:opacity-90"
    >
      Hang up
    </button>
  );
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

function InCallControls({ room, startedAt }: { room: Room; startedAt: number }) {
  const { state } = useVoiceAssistant();
  const [now, setNow] = useState(Date.now());
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, []);

  const toggleMute = async () => {
    await room.localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  };

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4">
      <div className="flex items-center gap-3">
        <span
          className={`size-3 rounded-full ${
            state === "speaking"
              ? "animate-pulse bg-ok"
              : state === "listening"
                ? "bg-accent"
                : "bg-line"
          }`}
        />
        <span className="font-medium" aria-live="polite">
          {STATE_LABEL[state] ?? state}
        </span>
        <span className="ml-auto font-mono text-sm text-muted tabular-nums">
          {formatClock((now - startedAt) / 1000)} / {formatClock(MAX_CALL_SECONDS)}
        </span>
      </div>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={toggleMute}
          className="rounded-full border border-line px-5 py-2 font-medium hover:bg-raised"
        >
          {muted ? "Unmute" : "Mute"}
        </button>
        <HangUp room={room} />
      </div>
      <StartAudio
        label="Tap to hear Mia"
        className="rounded-full bg-warn px-5 py-2 font-medium text-surface"
      />
    </section>
  );
}

/** The conversation while the call runs: LiveKit's live transcription plus Mia's events. */
function LiveConversation({
  room,
  events,
  details,
  onDetails,
  onLines,
}: {
  room: Room;
  events: MiaEvent[];
  details: boolean;
  onDetails: (on: boolean) => void;
  onLines: (lines: TranscriptLine[]) => void;
}) {
  const streams = useTranscriptions();
  const lines = toTranscript(streams, room.localParticipant.identity);
  // A block body: an effect must return nothing or a cleanup function. Returning the array
  // (an arrow with an expression body) crashed React mid-call and blanked the page.
  useEffect(() => {
    onLines(lines);
  }, [lines, onLines]);
  return (
    <Conversation
      items={buildConversation(lines, events)}
      live
      details={details}
      onDetails={onDetails}
    />
  );
}
