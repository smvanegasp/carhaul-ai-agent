import { Headphones, Phone, ShieldCheck } from "lucide-react";
import {
  RoomAudioRenderer,
  RoomContext,
  StartAudio,
  useMultibandTrackVolume,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { Room, RoomEvent } from "livekit-client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { CallError, fetchCall, fetchCallToken, wakeMia } from "../lib/api";
import { liveSnapshot } from "../lib/copy";
import { buildConversation } from "../lib/conversation";
import {
  addEvent,
  EVENTS_TOPIC,
  parseEvent,
  type MiaEvent,
} from "../lib/events";
import {
  formatClock,
  toTranscript,
  type TranscriptLine,
} from "../lib/transcript";
import { CallId } from "./CallId";
import { Conversation } from "./Conversation";
import { ErrorBoundary } from "./ErrorBoundary";
import { FeedbackForm } from "./FeedbackForm";
import { Insights } from "./Insights";
import { wakeProgress } from "../lib/wake";
import { useWake, type Wake } from "./useWake";
import { voiceAvatar, voiceName } from "./voiceAvatars";
import { useVoiceChoice, VoicePicker } from "./VoicePicker";
import { Button } from "../ui/button";

/** Mia hangs up at 6 minutes (agent/src/mia/main.py); the timer shows it. */
export const MAX_CALL_SECONDS = 6 * 60;

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
  if (name === "NotFoundError")
    return "No microphone found. Plug one in and call again.";
  return "Couldn't start the call. Please try again.";
}

/**
 * Layout (Belinda, 2026-11-17: the page grew as the transcript filled, and "Under the hood"
 * scrolled inside itself). The side column (call card, then Under the hood) is shown in full;
 * the conversation has a fixed height, scrolls inside, and on desktop stays in view (sticky)
 * while the page scrolls. So a growing transcript never changes the page's height. On a phone
 * the order is call card, conversation, Under the hood.
 */
export function CallPage() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const lastLines = useRef<TranscriptLine[]>([]);
  // Mia's events; kept after the call so the caller can look back at it.
  const [events, setEvents] = useState<MiaEvent[]>([]);
  const { wake, recheck } = useWake();
  const [details, setDetails] = useState(false);
  const voices = useVoiceChoice();
  const voiceLabel =
    voices.options.find((o) => o.key === voices.selected)?.label ?? null;

  const startCall = useCallback(async () => {
    setPhase({ kind: "connecting" });
    let room: Room | undefined;
    try {
      // The worker may have gone back to sleep while the page sat open: then wait again.
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
        setPhase({
          kind: "ended",
          roomName: token.room_name,
          lines: lastLines.current,
        }),
      );
      await room.connect(token.server_url, token.participant_token);
      await room.localParticipant.setMicrophoneEnabled(true);
      await room.startAudio(); // we're inside the click, so the browser lets audio play
      setPhase({ kind: "in-call", room, startedAt: Date.now() });
    } catch (err) {
      await room?.disconnect();
      const message =
        err instanceof CallError ? err.message : micErrorMessage(err);
      setPhase({ kind: "error", message });
    }
  }, [recheck, voices.selected]);

  const inCall = phase.kind === "in-call";
  const callCard = inCall ? (
    <ErrorBoundary fallback={<InCallFallback room={phase.room} />}>
      <InCallControls
        room={phase.room}
        startedAt={phase.startedAt}
        voiceLabel={voiceLabel}
      />
    </ErrorBoundary>
  ) : (
    <CallButtonCard
      phase={phase}
      wake={wake}
      onCall={startCall}
      onRetry={recheck}
      voiceLabel={voiceLabel}
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
      items={buildConversation(
        phase.kind === "ended" ? phase.lines : [],
        events,
      )}
      live={false}
      details={details}
      onDetails={setDetails}
      onCopy={
        phase.kind === "ended"
          ? async () => {
              // The saved record has everything; the worker writes it a few seconds after
              // the call, so until then the copy is what this page saw.
              try {
                return await fetchCall(phase.roomName);
              } catch {
                return liveSnapshot(phase.roomName, phase.lines, events);
              }
            }
          : undefined
      }
      footer={
        phase.kind === "ended" ? (
          <FeedbackForm key={phase.roomName} room={phase.roomName} />
        ) : undefined
      }
    />
  );

  const page = (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] lg:grid-rows-[auto_1fr]">
      <div className="lg:col-start-1 lg:row-start-1">{callCard}</div>
      {/* Fixed height: the transcript scrolls inside, the page doesn't grow. The desktop
          height is the screen minus the header, the title and the padding around them. */}
      <div className="flex h-[70dvh] min-h-[420px] flex-col lg:sticky lg:top-0 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:h-[calc(100dvh-13.5rem)] lg:self-start">
        <ErrorBoundary
          fallback={<Notice>The conversation view hit a display error.</Notice>}
        >
          {conversation}
        </ErrorBoundary>
      </div>
      <div className="lg:col-start-1 lg:row-start-2 lg:self-start">
        <ErrorBoundary fallback={<Notice>The stats hit a display error.</Notice>}>
          <Insights events={events} />
        </ErrorBoundary>
      </div>
    </div>
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
    <p className="rounded-2xl border border-line bg-surface p-4 text-sm text-muted">
      {children}
    </p>
  );
}

/**
 * Mia's card, the same before, during and after a call: the chosen voice's picture in the
 * animated orb, her name, and sound bars (looping when idle, Mia's real voice during a call).
 * ``children`` are the controls for the phase.
 */
function VoiceCard({
  voiceLabel,
  badge,
  bars,
  children,
}: {
  voiceLabel: string | null;
  badge: ReactNode;
  bars: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      data-tour="call-controls"
      aria-label="Call controls"
      className="mia-voice-card flex flex-col items-start gap-4 rounded-2xl p-4"
    >
      <div className="flex w-full items-center justify-between">
        <span className="mia-voice-badge eyebrow rounded-full px-2.5 py-1" aria-live="polite">
          {badge}
        </span>
      </div>
      <div className="flex w-full justify-center py-2">
        <div className="mia-orb">
          <span className="mia-orb-ring" aria-hidden="true" />
          <span className="mia-orb-ring mia-orb-ring-2" aria-hidden="true" />
          <img
            key={voiceLabel ?? "mia"}
            src={voiceAvatar(voiceLabel)}
            alt={`Mia speaking as ${voiceName(voiceLabel)}`}
            width={768}
            height={768}
            className="mia-orb-face"
          />
        </div>
      </div>
      <div className="w-full text-center">
        <h2 className="font-display text-4xl leading-none font-semibold tracking-tight">
          Mia
        </h2>
        <p className="mia-voice-muted mt-2 text-sm">
          Tell Mia your route and vehicle for an open-transport estimate.
        </p>
        {voiceLabel && (
          <p className="eyebrow mt-2">Voice · {voiceName(voiceLabel)}</p>
        )}
      </div>
      {bars}
      {children}
    </section>
  );
}

/** The looping sound bars of the idle card. */
function IdleBars() {
  return (
    <div className="voice-bars w-full" aria-hidden="true">
      {Array.from({ length: 25 }, (_, i) => (
        <span key={i} />
      ))}
    </div>
  );
}

/** Sound bars that follow Mia's voice during a call: 13 frequency bands, mirrored around
 * the middle bar, so they're still when she's quiet and move when she talks. */
function LiveBars() {
  const { audioTrack } = useVoiceAssistant();
  const bands = useMultibandTrackVolume(audioTrack, {
    bands: 13,
    loPass: 100,
    hiPass: 200,
  });
  const half = bands.length ? bands : Array.from({ length: 13 }, () => 0);
  const bars = [...half.slice(1).reverse(), ...half];
  return (
    <div className="voice-bars voice-bars-live w-full" aria-hidden="true">
      {bars.map((v, i) => (
        <span key={i} style={{ height: `${4 + Math.min(1, v * 1.6) * 44}px` }} />
      ))}
    </div>
  );
}

function CallButtonCard({
  phase,
  wake,
  onCall,
  onRetry,
  voicePicker,
  voiceLabel,
}: {
  voiceLabel: string | null;
  phase: Phase;
  wake: Wake;
  onCall: () => void;
  onRetry: () => void;
  voicePicker: ReactNode;
}) {
  const ready = wake.kind === "ready";
  return (
    <VoiceCard
      voiceLabel={voiceLabel}
      badge={ready ? "● Standing by" : "○ Waking up"}
      bars={<IdleBars />}
    >
      {voicePicker}
      <Button
        variant="ghost"
        type="button"
        onClick={onCall}
        disabled={phase.kind === "connecting" || !ready}
        className="h-12 w-full rounded-full bg-accent px-8 py-3.5 font-mono text-xs font-semibold tracking-wider text-brand uppercase shadow-sm transition hover:bg-accent hover:text-brand hover:opacity-90 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none disabled:cursor-wait disabled:opacity-60"
      >
        <Phone className="size-4" />
        {phase.kind === "connecting"
          ? "Calling…"
          : !ready
            ? "Mia is waking up…"
            : phase.kind === "ended"
              ? "Call again"
              : "Call Mia"}
      </Button>
      <div className="mia-voice-muted flex w-full justify-between gap-2 border-t border-line pt-3 font-mono text-[10px] tracking-wider uppercase">
        <span className="flex items-center gap-1">
          <Headphones className="size-3" /> Voice conversation
        </span>
        <span className="flex items-center gap-1">
          <ShieldCheck className="size-3" /> Up to {MAX_CALL_SECONDS / 60} minutes
        </span>
      </div>
      <WakeNote wake={wake} onRetry={onRetry} />
      {phase.kind === "error" && (
        <p role="alert" className="text-sm text-danger">
          {phase.message}
        </p>
      )}
      {phase.kind === "ended" && (
        <p className="mia-voice-muted text-sm">
          Call ended. Thanks for talking to Mia!{" "}
          <a
            href={`#/calls/${phase.roomName}`}
            className="font-medium text-accent underline-offset-2 hover:underline"
          >
            See this call in Past calls
          </a>
          <span className="mt-1 block">
            <CallId room={phase.roomName} />
          </span>
        </p>
      )}
      {phase.kind === "idle" && ready && (
        <div className="mia-voice-muted flex flex-col gap-2 text-sm">
          <p className="mia-voice-quote rounded-xl px-3 py-2">
            “I need to ship my 2020 Toyota Camry from Boston to Miami.”
          </p>
          <p>
            Your browser will ask for the microphone; headphones work best.
            The transfer demonstration routes to Sergio's phone, not a real agent.
          </p>
        </div>
      )}
    </VoiceCard>
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
      <div className="flex w-full flex-col gap-2 text-sm">
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
          Mia only runs when someone wants to call, so she takes about a minute
          to wake up. Keep this page open.
        </p>
      </div>
    );
  }
  if (wake.kind === "unavailable") {
    return (
      <p role="alert" className="text-sm text-danger">
        {wake.message}{" "}
        <Button variant="ghost" type="button" onClick={onRetry} className="underline">
          Try again
        </Button>
      </p>
    );
  }
  return null;
}

/** Shown if the call controls break: the call (and Mia's audio) keeps going. */
function InCallFallback({ room }: { room: Room }) {
  return (
    <section className="flex flex-col items-start gap-3 rounded-2xl border border-line bg-surface p-4">
      <p className="text-sm">
        You're still on the call with Mia; this view hit a display error.
      </p>
      <HangUp room={room} />
    </section>
  );
}

function HangUp({ room }: { room: Room }) {
  return (
    <Button
      variant="ghost"
      type="button"
      onClick={() => room.disconnect()}
      className="flex-1 rounded-full bg-danger px-5 py-2 font-medium text-surface hover:bg-danger hover:text-surface hover:opacity-90"
    >
      Hang up
    </Button>
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

/** The card during a call: the same picture and animations, Mia's live sound bars, and the
 * call controls instead of the voice picker (the voice can't change mid-call). */
function InCallControls({
  room,
  startedAt,
  voiceLabel,
}: {
  room: Room;
  startedAt: number;
  voiceLabel: string | null;
}) {
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
    <VoiceCard
      voiceLabel={voiceLabel}
      badge={`● ${STATE_LABEL[state] ?? state}`}
      bars={<LiveBars />}
    >
      <div className="flex w-full items-center justify-center font-mono text-sm text-muted tabular-nums">
        {formatClock((now - startedAt) / 1000)} / {formatClock(MAX_CALL_SECONDS)}
      </div>
      <div className="flex w-full gap-3">
        <Button
          variant="ghost"
          type="button"
          onClick={toggleMute}
          className="flex-1 rounded-full border border-line px-5 py-2 font-medium hover:bg-raised"
        >
          {muted ? "Unmute" : "Mute"}
        </Button>
        <HangUp room={room} />
      </div>
      <StartAudio
        label="Tap to hear Mia"
        className="w-full rounded-full bg-warn px-5 py-2 font-medium text-surface"
      />
    </VoiceCard>
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
      onCopy={() => Promise.resolve(liveSnapshot(room.name, lines, events))}
    />
  );
}
