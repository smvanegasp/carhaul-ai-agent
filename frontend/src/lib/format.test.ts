import { describe, expect, it } from "vitest";

import { formatDuration, formatUsd, outcomeLabel } from "./format";

describe("formatUsd", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(formatUsd(2729)).toBe("$2,729");
    expect(formatUsd(944)).toBe("$944");
  });
});

describe("call formatting", () => {
  it("durations", () => {
    expect(formatDuration(61.5)).toBe("1:02");
    expect(formatDuration(5)).toBe("0:05");
  });

  it("outcomes", () => {
    expect(outcomeLabel({ stage: "transfer", transfer: "connected" })).toBe(
      "Transferred to a representative",
    );
    expect(outcomeLabel({ stage: "quoted", quote_total: 724 })).toBe(
      "Got a quote",
    );
    expect(outcomeLabel({ stage: "greeting" })).toBe("Left at the greeting");
  });
});
