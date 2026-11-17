import mia from "../assets/mia-avatar.jpg";
import athena from "../assets/voice-athena.jpg";
import jessica from "../assets/voice-jessica.jpg";
import morgan from "../assets/voice-morgan.jpg";
import sarah from "../assets/voice-sarah.jpg";
import skylar from "../assets/voice-skylar.jpg";

/**
 * A picture for every voice (the voice names in backend/app/voices.py), matched by the name in
 * its label ("Cartesia · Skylar"). Thalia is the default voice, so she gets Mia's own picture.
 * Morgan is a female voice in Cartesia's catalog (Lovable first drew her as a man).
 */
const BY_NAME: Record<string, string> = {
  thalia: mia,
  athena,
  skylar,
  morgan,
  sarah,
  jessica,
};

export function voiceAvatar(label?: string | null): string {
  const l = (label ?? "").toLowerCase();
  for (const [name, src] of Object.entries(BY_NAME)) if (l.includes(name)) return src;
  return mia;
}

/** The voice's name from its label: "Deepgram · Thalia" -> "Thalia". */
export function voiceName(label?: string | null): string {
  const n = (label ?? "").split("·").pop()?.trim();
  return n || "Mia";
}
