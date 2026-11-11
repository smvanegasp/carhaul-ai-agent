import { describe, expect, it } from "vitest";

import { liveSnapshot, toJson } from "./copy";
import type { MiaEvent } from "./events";

describe("Copy JSON", () => {
  it("a live call carries its room, lines and events", () => {
    const events = [{ type: "turn", seq: 0, t: 1, at: 1, role: "mia", text: "Hi" }] as MiaEvent[];
    const lines = [{ id: "a", who: "you", text: "Hello", final: true, at: 2 }];
    const snap = liveSnapshot("call-1", lines as never, events, new Date("2026-11-11T00:00:00Z"));
    expect(snap.room).toBe("call-1");
    expect(snap.copied_at).toBe("2026-11-11T00:00:00.000Z");
    expect(snap.transcript).toBe(lines);
    expect(snap.events).toBe(events);
  });

  it("copies readable JSON", () => {
    expect(toJson({ a: 1 })).toBe('{\n  "a": 1\n}');
  });
});
