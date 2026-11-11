import { describe, expect, it } from "vitest";

import { buildConversation } from "./conversation";
import type { MiaEvent } from "./events";
import type { TranscriptLine } from "./transcript";

const line = (id: string, who: "you" | "mia", text: string, at: number): TranscriptLine => ({
  id,
  who,
  text,
  final: true,
  at,
});

const turn = (
  seq: number,
  role: "caller" | "mia",
  text: string,
  at: number,
  extra: Partial<MiaEvent> = {},
): MiaEvent =>
  ({
    type: "turn",
    seq,
    t: 0,
    at,
    role,
    kind: "said",
    text,
    metrics: {},
    speaking_s: null,
    interrupted: false,
    ...extra,
  }) as MiaEvent;

const tool = (seq: number, at: number): MiaEvent => ({
  type: "tool",
  seq,
  t: 0,
  at,
  name: "save_origin_destination",
  args: {},
  result: { ok: true },
  ok: true,
  ms: 700,
});

describe("buildConversation", () => {
  const lines = [
    line("g", "mia", "Hi, I'm Mia.", 1000),
    line("c1", "you", "Miami to Boston.", 5000),
    line("m1", "mia", "What car is it?", 8000),
  ];

  it("puts tool calls between the lines where they happened", () => {
    const items = buildConversation(lines, [tool(3, 7000)]);
    expect(items.map((i) => (i.kind === "line" ? i.id : i.kind))).toEqual([
      "g",
      "c1",
      "tool",
      "m1",
    ]);
  });

  it("attaches each turn's latency to its line", () => {
    const events = [
      turn(0, "mia", "Hi, I'm Mia.", 1100, { kind: "greeting" }),
      turn(1, "caller", "Miami to Boston.", 6500, { metrics: { end_of_turn: 577 } }),
      turn(2, "mia", "What car is it?", 9500, { metrics: { e2e: 1200 }, interrupted: true }),
    ];
    const items = buildConversation(lines, events);
    const byId = Object.fromEntries(items.flatMap((i) => (i.kind === "line" ? [[i.id, i]] : [])));
    expect(byId.g.note).toBe("greeting (from code)");
    expect(byId.c1.metrics).toEqual({ end_of_turn: 577 });
    expect(byId.m1.metrics).toEqual({ e2e: 1200 });
    expect(byId.m1.interrupted).toBe(true);
  });

  it("uses the turn events as lines when there is no transcription", () => {
    const items = buildConversation(
      [],
      [turn(0, "mia", "Hi", 1000), turn(1, "caller", "Yo", 6000)],
    );
    expect(items.map((i) => (i.kind === "line" ? [i.who, i.text] : i.kind))).toEqual([
      ["mia", "Hi"],
      ["you", "Yo"],
    ]);
  });

  it("falls back to seconds since start for events without a wall clock", () => {
    const old = { ...tool(5, 0), at: undefined, t: 6 } as MiaEvent;
    const items = buildConversation(
      [line("a", "you", "x", 5000), line("b", "mia", "y", 7000)],
      [old],
    );
    expect(items.map((i) => (i.kind === "line" ? i.id : i.kind))).toEqual(["a", "tool", "b"]);
  });
  it("without transcription, a caller line goes before the tool calls its reply made", () => {
    // The caller's turn event is logged after Mia's step ran (and dropped a call) at 10.0 s.
    const dropped: MiaEvent = {
      type: "dropped",
      seq: 1,
      t: 0,
      at: 10000,
      tool: "save_origin_destination",
      args: "{}",
      why: "no city the caller said",
    };
    const caller = turn(2, "caller", "Yeah, sure.", 10500, {
      speaking_s: 1,
      metrics: { end_of_turn: 577 },
    } as Partial<MiaEvent>);
    const items = buildConversation([], [dropped, caller]);
    expect(items.map((i) => i.kind)).toEqual(["line", "dropped"]);
  });
});

describe("screening lines (call-7334ef371604)", () => {
  const press =
    "Hi, this is Mia from F&F. I have a caller here about shipping 2 vehicles. Press 1 to take the call.";
  const events = [
    turn(1, "mia", "Please stay on the line.", 1000),
    turn(2, "mia", press, 5000, { kind: "handoff" }),
    turn(3, "mia", "Press 1 to take the call.", 9000, { kind: "handoff" }),
    turn(4, "mia", "No representative is available.", 12000, { kind: "transfer_failed" }),
  ];

  it("hides what Mia told the line when built from the record", () => {
    const texts = buildConversation([], events).map((i) => (i.kind === "line" ? i.text : ""));
    expect(texts).toEqual(["Please stay on the line.", "No representative is available."]);
  });

  it("hides the matching transcription lines too", () => {
    const lines = [
      line("a", "mia", "Please stay on the line.", 900),
      line("b", "mia", press, 4000),
      line("c", "mia", "Press 1 to take the call.", 8500),
      line("d", "mia", "No representative is available.", 11000),
    ];
    const ids = buildConversation(lines, events).map((i) => i.id);
    expect(ids).toEqual(["a", "d"]);
  });
});

it("hides Mia's goodbye to the line in older records (call-fde275e6bce5)", () => {
  const events = [
    turn(1, "mia", "Please stay on the line.", 1000),
    turn(2, "mia", "Thank you. I'll let you two talk now. Goodbye!", 5000, { kind: "handoff" }),
  ];
  const texts = buildConversation([], events).map((i) => (i.kind === "line" ? i.text : ""));
  expect(texts).toEqual(["Please stay on the line."]);
});
