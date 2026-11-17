import { describe, expect, it } from "vitest";

import mia from "../assets/mia-avatar.jpg";
import { voiceAvatar, voiceName } from "./voiceAvatars";

// The labels of backend/app/voices.py.
const LABELS = [
  "Deepgram · Thalia",
  "Deepgram · Athena",
  "Cartesia · Skylar",
  "Cartesia · Morgan",
  "ElevenLabs · Sarah",
  "ElevenLabs · Jessica",
];

describe("voice pictures", () => {
  it("gives the default voice (Thalia) Mia's picture", () => {
    expect(voiceAvatar("Deepgram · Thalia")).toBe(mia);
    expect(voiceAvatar(null)).toBe(mia);
  });

  it("has a picture for every voice, and only the default shares Mia's", () => {
    for (const label of LABELS) expect(voiceAvatar(label)).toBeTruthy();
    const others = LABELS.slice(1).map(voiceAvatar);
    expect(others).not.toContain(mia);
    expect(new Set(others).size).toBe(others.length);
  });

  it("reads the voice's name from its label", () => {
    expect(voiceName("Cartesia · Morgan")).toBe("Morgan");
    expect(voiceName(null)).toBe("Mia");
  });
});
