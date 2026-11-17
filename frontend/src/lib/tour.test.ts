import { describe, expect, it } from "vitest";
import { shouldStartTour } from "./tour";

describe("first-visit mini tutorial", () => {
  it("starts on the first visit after disclosure closes", () => {
    expect(shouldStartTour(false, null)).toBe(true);
    expect(shouldStartTour(true, null)).toBe(false);
  });
  it("does not repeat automatically after completion or skip", () => {
    expect(shouldStartTour(false, "1")).toBe(false);
  });
});