import { describe, expect, it } from "vitest";

import { transcriptFileName, transcriptText } from "./transcriptDelivery";

describe("the caller's transcript", () => {
  it("has only the dialogue, with the right speakers", () => {
    expect(
      transcriptText([
        { id: "1", who: "you", text: "Ship my Toyota to Miami.", final: true, at: 1 },
        { id: "2", who: "mia", text: "Where are we picking it up?", final: true, at: 2 },
        { id: "3", who: "you", text: "  ", final: true, at: 3 },
      ]),
    ).toBe("You: Ship my Toyota to Miami.\n\nMia: Where are we picking it up?");
  });

  it("is named after the call", () => {
    expect(transcriptFileName("call-0123456789ab")).toBe("mia-call-0123456789ab-transcript.txt");
  });
});
