import { describe, expect, it } from "vitest";

import { parseRoute, routeHash } from "./route";

describe("routes", () => {
  it("reads the hash", () => {
    expect(parseRoute("")).toEqual({ view: "call" });
    expect(parseRoute("#/")).toEqual({ view: "call" });
    expect(parseRoute("#/calls")).toEqual({ view: "calls", room: null });
    expect(parseRoute("#/calls/call-0123456789ab")).toEqual({
      view: "calls",
      room: "call-0123456789ab",
    });
  });

  it("round-trips", () => {
    for (const hash of ["#/", "#/calls", "#/calls/call-0123456789ab"]) {
      expect(routeHash(parseRoute(hash))).toBe(hash);
    }
  });
});
