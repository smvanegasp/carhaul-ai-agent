import { describe, expect, it } from "vitest";

import {
  buckets,
  formatSpan,
  funnel,
  inRange,
  kpis,
  story,
  type CallFacts,
} from "./stats";

const NOW = new Date(2026, 10, 10, 15, 0).getTime(); // Nov 10, 3 PM local

function call(daysAgo: number, f: Partial<CallFacts> = {}): CallFacts {
  const at = new Date(NOW - daysAgo * 86_400_000);
  return {
    room: `call-${daysAgo}-${Math.random()}`,
    started_at: at.toISOString(),
    test: false,
    duration_s: 120,
    mia_s: 120,
    route: false,
    vehicles: false,
    quoted: false,
    transfer: false,
    e2e_p50_ms: 1000,
    ...f,
  };
}

const QUOTED = { route: true, vehicles: true, quoted: true };
const ROWS = [
  call(0, { ...QUOTED, transfer: true, mia_s: 60 }),
  call(0, QUOTED),
  call(1, { route: true }),
  call(2),
  call(40, QUOTED),
];

describe("stats", () => {
  it("filters by range in local days", () => {
    expect(inRange(ROWS, "7d", NOW)).toHaveLength(4);
    expect(inRange(ROWS, "all", NOW)).toHaveLength(5);
  });

  it("computes the KPIs", () => {
    const k = kpis(inRange(ROWS, "7d", NOW));
    expect(k.calls).toBe(4);
    expect(k.transfers).toBe(1);
    expect(k.transferRate).toBe(0.25);
    expect(k.quotes).toBe(2);
    expect(k.miaSeconds).toBe(60 + 120 * 3);
    expect(k.avgMiaSeconds).toBe(105);
  });

  it("builds the funnel with step conversion", () => {
    const steps = funnel(inRange(ROWS, "7d", NOW));
    expect(steps.map((s) => s.count)).toEqual([4, 3, 2, 2, 1]);
    expect(steps[1].ofPrev).toBe(0.75);
    expect(steps[4].ofPrev).toBe(0.5);
    expect(steps[0].ofPrev).toBeNull();
  });

  it("fills every day of the range, zeros included", () => {
    const days = buckets(inRange(ROWS, "7d", NOW), "7d", NOW);
    expect(days).toHaveLength(7);
    expect(days.map((d) => d.calls)).toEqual([0, 0, 0, 0, 1, 1, 2]);
    expect(days[6].transfer).toBe(1);
  });

  it("switches to weeks for long ranges", () => {
    const weeks = buckets(ROWS, "all", NOW);
    expect(weeks.length).toBe(41); // 41 days stay daily; past 45 they become weeks
    const long = buckets([call(100), call(0)], "all", NOW);
    expect(long.length).toBeLessThan(20);
    expect(long.reduce((s, b) => s + b.calls, 0)).toBe(2);
  });

  it("tells the story", () => {
    const rows = inRange(ROWS, "7d", NOW);
    const text = story(kpis(rows), funnel(rows));
    expect(text).toContain(
      "Mia handled 4 calls (7 min a person didn't have to spend)",
    );
    expect(text).toContain(
      "1 qualified lead to a licensed representative (25% of calls)",
    );
    expect(text).toContain("biggest drop-off");
    expect(story(kpis([]), funnel([]))).toBe("No calls in this period yet.");
  });

  it("formats spans", () => {
    expect(formatSpan(45)).toBe("45 s");
    expect(formatSpan(95)).toBe("1 min 35 s");
    expect(formatSpan(4320)).toBe("1 h 12 min");
  });
});
