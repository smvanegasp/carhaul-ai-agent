import type { MiaEvent } from "./events";
import type { TranscriptLine } from "./transcript";

/**
 * "Copy JSON" on a call (Sergio's feedback, 2026-11-11): the whole call (transcript, tool calls
 * with their JSON, guardrail drops, latency) on the clipboard, to paste into a note or a chat
 * when something looks off.
 */

/** What a live call has before the worker saves its record: the same events plus the lines. */
export function liveSnapshot(
  room: string,
  lines: TranscriptLine[],
  events: MiaEvent[],
  now: Date = new Date(),
): Record<string, unknown> {
  return {
    room,
    copied_at: now.toISOString(),
    note: "live copy: the saved record (Past calls) appears once the call has ended",
    transcript: lines,
    events,
  };
}

export function toJson(data: unknown): string {
  return JSON.stringify(data, null, 2);
}

/** Copy text; true if it worked. The async clipboard needs a secure page and focus, so an
 * off-screen textarea is the fallback (ngrok and localhost previews included). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the textarea
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}
