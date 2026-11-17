/**
 * One conversation view: the chat lines (LiveKit's live transcription) with Mia's tool calls
 * and guardrail drops placed between them, and each line's latency from her events.
 *
 * Lines and events carry wall-clock times from the same clock (the worker's), so they sort
 * together. A turn event arrives when its line is done, so it belongs to the latest line of
 * the same speaker that started before it. If there are no transcription lines (they can be
 * missing after a reconnect), the turn events themselves become the lines. A Mia turn with no
 * line of its own is shown from its event: the greeting starts as the call connects, before
 * the page listens to the transcription (call d9dfdc6763f5, 2026-11-17: the greeting was
 * missing from the live view, but it was in the record). Lines spoken from code (the greeting,
 * fillers) are logged as they start, with their whole text, while the transcription is still
 * spelling them out word by word: such an event belongs to the line its text starts with
 * (Belinda, 2026-11-17: the whole greeting showed before Mia said it, then again as she
 * spoke). With no transcription of it, the event's text is revealed word by word at the
 * voice's pace (`spokenSoFar`).
 */

import type {
  DroppedEvent,
  MiaEvent,
  ToolEvent,
  TurnEvent,
  TurnMetrics,
} from "./events";
import type { TranscriptLine } from "./transcript";

export type ConversationItem =
  | {
      kind: "line";
      id: string;
      who: "you" | "mia";
      text: string;
      final: boolean;
      at: number;
      /** Set once Mia's event for this turn arrives. */
      metrics?: TurnMetrics;
      note?: string;
      interrupted?: boolean;
    }
  | { kind: "tool"; id: string; at: number; event: ToolEvent }
  | { kind: "dropped"; id: string; at: number; event: DroppedEvent };

const NOTES: Record<string, string> = {
  greeting: "greeting (from code)",
  filler: "filler line (from code)",
  time_limit: "time limit (from code)",
  handoff: "handoff to the representative (from code)",
  transfer_failed: "transfer not answered (from code)",
  silence: "the caller went quiet (from code)",
};

/**
 * What Mia told the representative's line while it was screened ("...Press 1 to take the
 * call."). The caller never hears it, so it isn't part of the conversation (Belinda,
 * 2026-11-11). Newer calls don't log it as a turn at all; this hides it in older records.
 */
export function isScreening(t: TurnEvent): boolean {
  return t.kind === "handoff" && /press 1 to take the call|let you two talk now/i.test(t.text);
}

/** For comparing texts: lower case, no punctuation, single spaces. */
function norm(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function eventTime(e: MiaEvent): number {
  // Older events (before "at" existed) only have seconds since the call started.
  return e.at ?? e.t * 1000;
}

/**
 * When a turn's line started, from its event (logged when the turn is done; for the caller,
 * only once Mia's reply is under way, after her tool calls). Only used without transcription.
 */
function lineStart(t: TurnEvent): number {
  const spoke = (t.speaking_s ?? 0) * 1000;
  const waited = t.role === "caller" ? (t.metrics.end_of_turn ?? 0) + 2000 : 0;
  return eventTime(t) - spoke - waited;
}

/** Roughly how fast the voices speak, and how long before the first word is heard. */
const MS_PER_WORD = 360;
const FIRST_WORD_MS = 500;

/**
 * Live, a line spoken from code (logged as it starts, with its whole text) is shown word by
 * word at about the voice's pace, like the transcription would: the greeting often has no
 * transcription because it starts before the page listens (Belinda, 2026-11-17: it popped in
 * whole). Lines from the LLM are logged when done, so they are shown whole. ``null``: nothing
 * heard yet.
 */
export function spokenSoFar(
  t: TurnEvent,
  now: number | undefined,
): { text: string; final: boolean } | null {
  if (now === undefined || t.role !== "mia" || t.kind === "said")
    return { text: t.text, final: true };
  const words = t.text.split(/\s+/).filter(Boolean);
  const heard = Math.floor((now - eventTime(t) - FIRST_WORD_MS) / MS_PER_WORD) + 1;
  if (heard <= 0) return null;
  if (heard >= words.length) return { text: t.text, final: true };
  return { text: words.slice(0, heard).join(" "), final: false };
}

/**
 * ``now`` (live calls only): the time on the worker's clock, so lines spoken from code are
 * revealed as they are said. Without it (saved calls) every line is whole.
 */
export function buildConversation(
  lines: TranscriptLine[],
  events: MiaEvent[],
  now?: number,
): ConversationItem[] {
  const allTurns = events.filter((e): e is TurnEvent => e.type === "turn");
  const turns = allTurns.filter((t) => !isScreening(t));
  const screening = allTurns.filter(isScreening);
  const items: ConversationItem[] =
    lines.length > 0
      ? lines.map((l) => ({ kind: "line" as const, ...l }))
      : turns.flatMap((t) => {
          const spoken = spokenSoFar(t, now);
          if (!spoken) return [];
          return [
            {
              kind: "line" as const,
              id: `turn-${t.seq}`,
              who: t.role === "caller" ? ("you" as const) : ("mia" as const),
              text: spoken.text,
              final: spoken.final,
              at: lineStart(t),
            },
          ];
        });

  // Attach each turn's metrics to its line.
  const claimed = new Set<string>();
  const unmatched: TurnEvent[] = [];
  for (const t of turns) {
    const who = t.role === "caller" ? "you" : "mia";
    const at = eventTime(t);
    const at2 = lines.length > 0 ? at : lineStart(t);
    let match: (ConversationItem & { kind: "line" }) | undefined;
    for (const item of items) {
      if (item.kind !== "line" || item.who !== who || claimed.has(item.id))
        continue;
      if (item.at <= Math.max(at, at2) + 1000) match = item; // latest line started before it
    }
    if (!match) {
      unmatched.push(t);
      continue;
    }
    claimed.add(match.id);
    match.metrics = t.metrics;
    match.note = NOTES[t.kind];
    match.interrupted = t.interrupted;
  }

  // Mia's lines the transcription missed, from their events. A line whose text starts the
  // event's (or the other way round) is the same speech, still being transcribed.
  const miaLines = items.filter(
    (i): i is ConversationItem & { kind: "line" } => i.kind === "line" && i.who === "mia",
  );
  const lastLineAt = Math.max(-Infinity, ...lines.map((l) => l.at));
  for (const t of unmatched) {
    if (t.role !== "mia") continue;
    const said = norm(t.text);
    const same = miaLines.find((l) => {
      const text = norm(l.text);
      return text.length > 0 && (said.startsWith(text) || text.startsWith(said));
    });
    if (same) {
      if (!claimed.has(same.id)) {
        claimed.add(same.id);
        same.metrics = t.metrics;
        same.note = NOTES[t.kind];
        same.interrupted = t.interrupted;
      }
      continue;
    }
    // A line from the LLM with no transcription yet: wait for a later line (it may still come).
    if (lines.length > 0 && t.kind === "said" && lastLineAt <= eventTime(t)) continue;
    const spoken = spokenSoFar(t, now);
    if (!spoken) continue;
    items.push({
      kind: "line",
      id: `turn-${t.seq}`,
      who: "mia",
      text: spoken.text,
      final: spoken.final,
      at: lineStart(t),
      metrics: t.metrics,
      note: NOTES[t.kind],
      interrupted: t.interrupted,
    });
  }

  // A transcription line that is a screening line: dropped (same text, Mia's side).
  const hidden = new Set(screening.map((t) => t.text.trim().toLowerCase()));
  const shown = items.filter(
    (i) =>
      i.kind !== "line" ||
      i.who !== "mia" ||
      !hidden.has(i.text.trim().toLowerCase()),
  );
  items.length = 0;
  items.push(...shown);

  for (const e of events) {
    if (e.type === "tool")
      items.push({
        kind: "tool",
        id: `ev-${e.seq}`,
        at: eventTime(e),
        event: e,
      });
    if (e.type === "dropped") {
      items.push({
        kind: "dropped",
        id: `ev-${e.seq}`,
        at: eventTime(e),
        event: e,
      });
    }
  }
  return items.sort((a, b) => a.at - b.at);
}
