/**
 * One conversation view: the chat lines (LiveKit's live transcription) with Mia's tool calls
 * and guardrail drops placed between them, and each line's latency from her events.
 *
 * Lines and events carry wall-clock times from the same clock (the worker's), so they sort
 * together. A turn event arrives when its line is done, so it belongs to the latest line of
 * the same speaker that started before it. If there are no transcription lines (they can be
 * missing after a reconnect), the turn events themselves become the lines.
 */

import type { DroppedEvent, MiaEvent, ToolEvent, TurnEvent, TurnMetrics } from "./events";
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
};

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

export function buildConversation(lines: TranscriptLine[], events: MiaEvent[]): ConversationItem[] {
  const turns = events.filter((e): e is TurnEvent => e.type === "turn");
  const items: ConversationItem[] =
    lines.length > 0
      ? lines.map((l) => ({ kind: "line" as const, ...l }))
      : turns.map((t) => ({
          kind: "line" as const,
          id: `turn-${t.seq}`,
          who: t.role === "caller" ? ("you" as const) : ("mia" as const),
          text: t.text,
          final: true,
          at: lineStart(t),
        }));

  // Attach each turn's metrics to its line.
  const claimed = new Set<string>();
  for (const t of turns) {
    const who = t.role === "caller" ? "you" : "mia";
    const at = eventTime(t);
    const at2 = lines.length > 0 ? at : lineStart(t);
    let match: (ConversationItem & { kind: "line" }) | undefined;
    for (const item of items) {
      if (item.kind !== "line" || item.who !== who || claimed.has(item.id)) continue;
      if (item.at <= Math.max(at, at2) + 1000) match = item; // latest line started before it
    }
    if (!match) continue;
    claimed.add(match.id);
    match.metrics = t.metrics;
    match.note = NOTES[t.kind];
    match.interrupted = t.interrupted;
  }

  for (const e of events) {
    if (e.type === "tool")
      items.push({ kind: "tool", id: `ev-${e.seq}`, at: eventTime(e), event: e });
    if (e.type === "dropped") {
      items.push({ kind: "dropped", id: `ev-${e.seq}`, at: eventTime(e), event: e });
    }
  }
  return items.sort((a, b) => a.at - b.at);
}
