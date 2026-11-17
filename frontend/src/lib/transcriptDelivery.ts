import type { TranscriptLine } from "./transcript";

/** The caller's copy of the call: only the dialogue (no tool calls, latency or feedback). */
export function transcriptText(lines: TranscriptLine[]): string {
  return lines
    .filter((line) => line.text.trim())
    .map((line) => `${line.who === "mia" ? "Mia" : "You"}: ${line.text.trim()}`)
    .join("\n\n");
}

export function transcriptFileName(room: string): string {
  return `mia-${room}-transcript.txt`;
}
