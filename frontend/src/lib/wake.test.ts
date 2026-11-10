import { describe, expect, it } from "vitest";

import { wakeProgress } from "./wake";

describe("wakeProgress", () => {
  it("starts near zero and moves with time", () => {
    expect(wakeProgress(0, "server").percent).toBe(0);
    expect(wakeProgress(20_000, "server").percent).toBeGreaterThan(20);
  });

  it("stays under half while ECS is still getting a server", () => {
    expect(wakeProgress(60_000, "server")).toEqual({
      percent: 50,
      label: "Getting a server ready",
    });
  });

  it("jumps past half once the container runs", () => {
    expect(wakeProgress(5_000, "loading")).toEqual({
      percent: 55,
      label: "Loading Mia's voice and models",
    });
  });

  it("never claims to be done before Mia is ready", () => {
    expect(wakeProgress(10 * 60_000, "loading").percent).toBe(95);
    expect(wakeProgress(10 * 60_000, null).percent).toBe(95);
  });

  it("guesses the step from time when the API doesn't say", () => {
    expect(wakeProgress(10_000, null).label).toBe("Getting a server ready");
    expect(wakeProgress(50_000, null).label).toBe(
      "Loading Mia's voice and models",
    );
  });
});
