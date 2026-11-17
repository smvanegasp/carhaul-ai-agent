import { describe, expect, it } from "vitest";

import { groupByMonth, monthKey } from "./months";

describe("groupByMonth", () => {
  it("groups calls by month, newest first, keeping their order", () => {
    const calls = [
      { room: "c", started_at: "2026-11-17T15:00:00" },
      { room: "b", started_at: "2026-11-02T15:00:00" },
      { room: "a", started_at: "2026-10-20T15:00:00" },
    ];
    const groups = groupByMonth(calls);
    expect(
      groups.map((g) => [g.key, g.label, g.calls.map((c) => c.room)]),
    ).toEqual([
      ["2026-11", "November 2026", ["c", "b"]],
      ["2026-10", "October 2026", ["a"]],
    ]);
  });

  it("puts a call with a broken date in its own group", () => {
    expect(monthKey("not a date")).toBe("unknown");
    expect(groupByMonth([{ started_at: "nope" }])[0].label).toBe(
      "Unknown date",
    );
  });

  it("is empty for no calls", () => {
    expect(groupByMonth([])).toEqual([]);
  });
});
