import { describe, expect, it, vi } from "vitest";

import { sendFeedback } from "./api";
import { addEvent, formatMs, median, parseEvent, toPanel, type MiaEvent } from "./events";

const turn = (seq: number, role: "caller" | "mia", text: string, metrics = {}): MiaEvent => ({
  type: "turn",
  seq,
  t: seq,
  role,
  kind: "said",
  text,
  metrics,
  speaking_s: null,
  interrupted: false,
});

describe("parseEvent", () => {
  it("accepts known event types", () => {
    expect(parseEvent('{"type":"tool","seq":3,"t":1.2,"name":"get_quote"}')?.type).toBe("tool");
  });

  it("ignores anything else", () => {
    expect(parseEvent("not json")).toBeNull();
    expect(parseEvent('{"type":"mystery","seq":1}')).toBeNull();
    expect(parseEvent('{"type":"turn"}')).toBeNull();
  });
});

describe("addEvent", () => {
  it("keeps the worker's order and drops repeats", () => {
    let events: MiaEvent[] = [];
    events = addEvent(events, turn(1, "caller", "b"));
    events = addEvent(events, turn(0, "mia", "a"));
    events = addEvent(events, turn(1, "caller", "b"));
    expect(events.map((e) => e.seq)).toEqual([0, 1]);
  });
});

describe("toPanel", () => {
  it("builds the timeline, what's on file and the latency medians", () => {
    const events: MiaEvent[] = [
      { type: "config", seq: 0, t: 0, llm: "Groq openai/gpt-oss-20b" },
      turn(1, "caller", "Miami to Boston", { end_of_turn: 577, stt: 300 }),
      {
        type: "tool",
        seq: 2,
        t: 2,
        name: "save_origin_destination",
        args: { origin_city: "Miami" },
        result: { ok: true },
        ok: true,
        ms: 210,
      },
      {
        type: "state",
        seq: 3,
        t: 2,
        stage: "route",
        quote: null,
        on_file: {
          origin: "Miami, Florida",
          destination: "Boston, Massachusetts",
          vehicles: [],
          expected_vehicles: null,
          missing: ["vehicle"],
        },
      },
      { type: "dropped", seq: 4, t: 2, tool: "save_vehicle", args: "{}", why: "not said" },
      turn(5, "mia", "What car?", { llm_ttft: 300, tts_ttfb: 170, e2e: 1000 }),
      turn(6, "mia", "Thanks.", { llm_ttft: 200, tts_ttfb: 150, e2e: 1400 }),
      {
        type: "tool",
        seq: 7,
        t: 9,
        name: "get_quote",
        args: {},
        result: { ok: false },
        ok: false,
        ms: 900,
      },
      { type: "end", seq: 8, t: 10, end_reason: "mia", stage: "quoted" },
    ];
    const panel = toPanel(events);
    expect(panel.config?.llm).toBe("Groq openai/gpt-oss-20b");
    expect(panel.timeline.map((e) => e.type)).toEqual([
      "turn",
      "tool",
      "dropped",
      "turn",
      "turn",
      "tool",
      "end",
    ]);
    expect(panel.onFile?.origin).toBe("Miami, Florida");
    expect(panel.stage).toBe("quoted");
    expect(panel.toolCalls).toBe(2);
    expect(panel.toolErrors).toBe(1);
    expect(panel.dropped).toBe(1);
    expect(panel.latency.e2e).toEqual({ median: 1200, last: 1400, n: 2 });
    expect(panel.latency.end_of_turn).toEqual({ median: 577, last: 577, n: 1 });
    expect(panel.ended?.end_reason).toBe("mia");
  });

  it("starts empty", () => {
    const panel = toPanel([]);
    expect(panel.timeline).toEqual([]);
    expect(panel.latency.e2e.median).toBeNull();
  });
});

describe("helpers", () => {
  it("median and formatMs", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([])).toBeNull();
    expect(formatMs(850)).toBe("850 ms");
    expect(formatMs(1250)).toBe("1.25 s");
    expect(formatMs(null)).toBe("–");
  });
});

describe("sendFeedback", () => {
  it("posts to the call's feedback endpoint", async () => {
    const fetchFn = vi.fn(async () => new Response("{}", { status: 201 }));
    await sendFeedback("call-abc", { rating: 4, comment: "ok", persona: "" }, fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/calls/call-abc/feedback",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows the server's message on errors", async () => {
    const fetchFn = vi.fn(
      async () => new Response(JSON.stringify({ detail: "Slow down" }), { status: 429 }),
    );
    await expect(
      sendFeedback("call-abc", { rating: 4, comment: "", persona: "" }, fetchFn),
    ).rejects.toThrow("Slow down");
  });
});
