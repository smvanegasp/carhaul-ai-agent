/**
 * Mia's call events (topic "mia.events"), as sent by the worker: agent/src/mia/events.py
 * documents each type. The live panel is built from them with `toPanel`.
 */

export const EVENTS_TOPIC = "mia.events";

interface Base {
  seq: number;
  /** Seconds since the call started. */
  t: number;
}

export interface ConfigEvent extends Base {
  type: "config";
  stt?: string;
  llm?: string;
  tts?: string;
  turn_detector?: string;
  max_call_s?: string;
}

export interface TurnMetrics {
  end_of_turn?: number;
  stt?: number;
  llm_ttft?: number;
  tts_ttfb?: number;
  e2e?: number;
}

export interface TurnEvent extends Base {
  type: "turn";
  role: "caller" | "mia";
  kind: "said" | "greeting" | "filler" | "time_limit";
  text: string;
  metrics: TurnMetrics;
  speaking_s: number | null;
  interrupted: boolean;
}

export interface ToolEvent extends Base {
  type: "tool";
  name: string;
  args: unknown;
  result: unknown;
  ok: boolean;
  ms: number;
}

export interface DroppedEvent extends Base {
  type: "dropped";
  tool: string;
  args: string;
  why: string;
}

export interface OnFile {
  origin: string | null;
  destination: string | null;
  vehicles: { quote_id: string; vehicle: string; estimate_by_type?: boolean; drivable?: boolean }[];
  expected_vehicles: number | null;
  missing: string[];
}

export interface StateEvent extends Base {
  type: "state";
  on_file: OnFile;
  stage: string;
  quote: { total?: number; transit_days?: [number, number] } | null;
}

export interface EndEvent extends Base {
  type: "end";
  end_reason: string | null;
  stage: string;
}

export type MiaEvent = ConfigEvent | TurnEvent | ToolEvent | DroppedEvent | StateEvent | EndEvent;

const TYPES = new Set(["config", "turn", "tool", "dropped", "state", "end"]);

/** One message from the stream, or null if it isn't an event we know. */
export function parseEvent(text: string): MiaEvent | null {
  try {
    const value: unknown = JSON.parse(text);
    if (
      value &&
      typeof value === "object" &&
      TYPES.has((value as { type?: string }).type ?? "") &&
      typeof (value as { seq?: unknown }).seq === "number"
    ) {
      return value as MiaEvent;
    }
  } catch {
    // not JSON: ignore
  }
  return null;
}

/** Adds an event, keeping them in the worker's order and ignoring repeats. */
export function addEvent(events: MiaEvent[], event: MiaEvent): MiaEvent[] {
  if (events.some((e) => e.seq === event.seq)) return events;
  return [...events, event].sort((a, b) => a.seq - b.seq);
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

/** The latency components the panel shows, in pipeline order. */
export const LATENCY_PARTS = [
  { key: "end_of_turn", label: "End of turn", side: "caller" },
  { key: "stt", label: "Speech to text", side: "caller" },
  { key: "llm_ttft", label: "LLM first token", side: "mia" },
  { key: "tts_ttfb", label: "Voice first audio", side: "mia" },
  { key: "e2e", label: "Total (e2e)", side: "mia" },
] as const;

export type LatencyKey = (typeof LATENCY_PARTS)[number]["key"];

export interface Panel {
  config: ConfigEvent | null;
  /** Everything except config and state, oldest first. */
  timeline: (TurnEvent | ToolEvent | DroppedEvent | EndEvent)[];
  onFile: OnFile | null;
  stage: string;
  quoteTotal: number | null;
  /** Median and last value per component, in ms. */
  latency: Record<LatencyKey, { median: number | null; last: number | null; n: number }>;
  toolCalls: number;
  toolErrors: number;
  dropped: number;
  ended: EndEvent | null;
}

export function toPanel(events: MiaEvent[]): Panel {
  const values: Record<LatencyKey, number[]> = {
    end_of_turn: [],
    stt: [],
    llm_ttft: [],
    tts_ttfb: [],
    e2e: [],
  };
  const panel: Panel = {
    config: null,
    timeline: [],
    onFile: null,
    stage: "greeting",
    quoteTotal: null,
    latency: {} as Panel["latency"],
    toolCalls: 0,
    toolErrors: 0,
    dropped: 0,
    ended: null,
  };
  for (const e of events) {
    switch (e.type) {
      case "config":
        panel.config = e;
        break;
      case "state":
        panel.onFile = e.on_file;
        panel.stage = e.stage;
        panel.quoteTotal = e.quote?.total ?? null;
        break;
      case "turn":
        for (const { key } of LATENCY_PARTS) {
          const v = e.metrics[key];
          if (typeof v === "number") values[key].push(v);
        }
        panel.timeline.push(e);
        break;
      case "tool":
        panel.toolCalls += 1;
        if (!e.ok) panel.toolErrors += 1;
        panel.timeline.push(e);
        break;
      case "dropped":
        panel.dropped += 1;
        panel.timeline.push(e);
        break;
      case "end":
        panel.ended = e;
        panel.stage = e.stage;
        panel.timeline.push(e);
        break;
    }
  }
  for (const { key } of LATENCY_PARTS) {
    const v = values[key];
    panel.latency[key] = { median: median(v), last: v.at(-1) ?? null, n: v.length };
  }
  return panel;
}

/** "850 ms" or "1.25 s". */
export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "–";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}
