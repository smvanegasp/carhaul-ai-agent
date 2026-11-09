import { describe, expect, it } from "vitest";

import { fetchCallToken } from "./api";
import { formatClock, toTranscript, type TranscriptStream } from "./transcript";

const stream = (
  who: string,
  text: string,
  segment: string,
  at: number,
  final = true,
): TranscriptStream => ({
  text,
  participantInfo: { identity: who },
  streamInfo: {
    id: `${segment}-${at}`,
    timestamp: at,
    attributes: { "lk.segment_id": segment, "lk.transcription_final": String(final) },
  },
});

describe("toTranscript", () => {
  it("orders lines by when each segment started and labels the speaker", () => {
    const lines = toTranscript(
      [
        stream("caller-1", "Yeah sure.", "u1", 20),
        stream("agent-1", "Hi, thanks for calling F&F.", "a1", 10),
      ],
      "caller-1",
    );
    expect(lines.map((l) => [l.who, l.text])).toEqual([
      ["mia", "Hi, thanks for calling F&F."],
      ["you", "Yeah sure."],
    ]);
  });

  it("replaces interim text of the same segment, keeping its position", () => {
    const lines = toTranscript(
      [
        stream("caller-1", "From Mia", "u1", 10, false),
        stream("agent-1", "Got it.", "a1", 15),
        stream("caller-1", "From Miami, Florida.", "u1", 20),
      ],
      "caller-1",
    );
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ who: "you", text: "From Miami, Florida.", final: true });
  });

  it("skips empty segments", () => {
    expect(toTranscript([stream("agent-1", "  ", "a1", 1)], "me")).toEqual([]);
  });
});

describe("formatClock", () => {
  it("formats minutes and seconds", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65.7)).toBe("1:05");
    expect(formatClock(360)).toBe("6:00");
  });
});

describe("fetchCallToken", () => {
  const respond = (status: number, body: unknown) => async () =>
    new Response(JSON.stringify(body), { status });

  it("returns the token", async () => {
    const token = { server_url: "wss://x", participant_token: "t", room_name: "call-1" };
    await expect(fetchCallToken(respond(200, token))).resolves.toEqual(token);
  });

  it("shows the server's message when rate limited", async () => {
    const detail = "That's a lot of calls in a short time. Try again in a bit.";
    await expect(fetchCallToken(respond(429, { detail }))).rejects.toThrow(detail);
  });

  it("has a fallback message", async () => {
    await expect(fetchCallToken(respond(500, "oops"))).rejects.toThrow("error 500");
  });
});
