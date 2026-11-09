import { describe, expect, it } from "vitest";

import { formatUsd } from "./format";

describe("formatUsd", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(formatUsd(2729)).toBe("$2,729");
    expect(formatUsd(944)).toBe("$944");
  });
});
