import { afterEach, describe, expect, it, vi } from "vitest";
import { copyrightYear } from "./calendar";

afterEach(() => vi.useRealTimers());

describe("automatic footer year", () => {
  it("changes from 2026 to 2027 when the new year arrives", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59, 59));
    expect(copyrightYear()).toBe(2026);
    vi.setSystemTime(new Date(2027, 0, 1));
    expect(copyrightYear()).toBe(2027);
  });

  it("continues updating in subsequent years", () => {
    expect(copyrightYear(new Date(2028, 0, 1))).toBe(2028);
    expect(copyrightYear(new Date(2029, 0, 1))).toBe(2029);
  });
});