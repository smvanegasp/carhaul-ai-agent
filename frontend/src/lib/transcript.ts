/** Minimal shape of a LiveKit transcription text stream (TextStreamData in components-core). */
export interface TranscriptStream {
  text: string;
  participantInfo: { identity: string };
  streamInfo: { id: string; timestamp: number; attributes?: Record<string, string> };
}

export interface TranscriptLine {
  id: string;
  who: "you" | "mia";
  text: string;
  final: boolean;
  /** When the line started (epoch ms, the sender's clock: the worker for both sides). */
  at: number;
}

/**
 * Turns LiveKit's transcription streams into chat lines, oldest first. Each segment
 * ("lk.segment_id") is one line; interim versions of the same segment replace each other, so
 * the caller sees their words appear while they talk.
 */
export function toTranscript(streams: TranscriptStream[], myIdentity: string): TranscriptLine[] {
  const bySegment = new Map<string, TranscriptLine>();
  for (const s of streams) {
    const attrs = s.streamInfo.attributes ?? {};
    const id = attrs["lk.segment_id"] ?? s.streamInfo.id;
    const text = s.text.trim();
    if (!text) continue;
    const prev = bySegment.get(id);
    bySegment.set(id, {
      id,
      who: s.participantInfo.identity === myIdentity ? "you" : "mia",
      text,
      final: attrs["lk.transcription_final"] === "true",
      at: prev ? prev.at : s.streamInfo.timestamp,
    });
  }
  return [...bySegment.values()].sort((a, b) => a.at - b.at);
}

/** "m:ss" for the call timer. */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
