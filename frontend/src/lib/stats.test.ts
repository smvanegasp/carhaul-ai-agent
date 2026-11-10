import { describe, expect, it } from "vitest";

import {
  dispositions,
  formatSpan,
  funnel,
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
    disposition: f.transfer ? "organic_transfer" : "hung_up",
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
  it("computes the KPIs", () => {
    const k = kpis(ROWS.slice(0, 4));
    expect(k.calls).toBe(4);
    expect(k.transfers).toBe(1);
    expect(k.transferRate).toBe(0.25);
    expect(k.quotes).toBe(2);
    expect(k.miaSeconds).toBe(60 + 120 * 3);
    expect(k.avgMiaSeconds).toBe(105);
  });

  it("builds the funnel with step conversion", () => {
    const steps = funnel(ROWS.slice(0, 4));
    expect(steps.map((s) => s.count)).toEqual([4, 3, 2, 2, 1]);
    expect(steps[1].ofPrev).toBe(0.75);
    expect(steps[4].ofPrev).toBe(0.5);
    expect(steps[0].ofPrev).toBeNull();
  });

  it("counts dispositions, leads first", () => {
    const d = dispositions(ROWS);
    expect(d.filter((x) => x.lead).map((x) => x.key)).toEqual([
      "organic_transfer",
      "requested_transfer",
      "forced_transfer",
    ]);
    expect(d.find((x) => x.key === "organic_transfer")?.count).toBe(1);
    expect(d.find((x) => x.key === "hung_up")?.share).toBe(4 / 5);
  });

  it("tells the story", () => {
    const rows = ROWS.slice(0, 4);
    const text = story(kpis(rows), funnel(rows));
    expect(text).toContain(
      "Mia handled 4 calls (7 min a person didn't have to spend)",
    );
    expect(text).toContain(
      "1 qualified lead to a licensed representative (25% of calls)",
    );
    expect(text).toContain("biggest drop-off");
    expect(story(kpis([]), funnel([]))).toBe("No calls yet.");
  });

  it("formats spans", () => {
    expect(formatSpan(45)).toBe("45 s");
    expect(formatSpan(95)).toBe("1 min 35 s");
    expect(formatSpan(4320)).toBe("1 h 12 min");
  });
});
