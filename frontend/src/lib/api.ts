/** What POST /api/token returns (backend/app/livekit_token.py). */
export interface CallToken {
  server_url: string;
  participant_token: string;
  room_name: string;
}

/** Thrown with a message that can be shown to the caller as is. */
export class CallError extends Error {}

export async function fetchCallToken(fetchFn: typeof fetch = fetch): Promise<CallToken> {
  let res: Response;
  try {
    res = await fetchFn("/api/token", { method: "POST" });
  } catch {
    throw new CallError("Can't reach the server. Check your connection and try again.");
  }
  if (res.ok) return (await res.json()) as CallToken;
  // 429 (rate limit, daily cap) and 503 (not configured) carry a friendly detail.
  const detail = await res
    .json()
    .then((b: { detail?: unknown }) => (typeof b.detail === "string" ? b.detail : null))
    .catch(() => null);
  throw new CallError(detail ?? `Mia can't take calls right now (error ${res.status}).`);
}

export interface FeedbackIn {
  rating: number;
  comment: string;
  persona: string;
}

/** POST /api/calls/{room}/feedback (backend/app/calls.py). */
export async function sendFeedback(
  room: string,
  feedback: FeedbackIn,
  fetchFn: typeof fetch = fetch,
): Promise<void> {
  let res: Response;
  try {
    res = await fetchFn(`/api/calls/${encodeURIComponent(room)}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(feedback),
    });
  } catch {
    throw new CallError("Can't reach the server. Check your connection and try again.");
  }
  if (res.ok) return;
  const detail = await res
    .json()
    .then((b: { detail?: unknown }) => (typeof b.detail === "string" ? b.detail : null))
    .catch(() => null);
  throw new CallError(detail ?? `Couldn't send your feedback (error ${res.status}).`);
}

/** What POST /api/wake returns (backend/app/worker.py). */
export interface WakeStatus {
  state: "ready" | "starting" | "unavailable";
  detail: string;
}

/** Ask for Mia's voice worker (on AWS it only runs around calls; starting takes ~1 minute). */
export async function wakeMia(fetchFn: typeof fetch = fetch): Promise<WakeStatus> {
  let res: Response;
  try {
    res = await fetchFn("/api/wake", { method: "POST" });
  } catch {
    throw new CallError("Can't reach the server. Check your connection and try again.");
  }
  if (res.ok) return (await res.json()) as WakeStatus;
  const detail = await res
    .json()
    .then((b: { detail?: unknown }) => (typeof b.detail === "string" ? b.detail : null))
    .catch(() => null);
  throw new CallError(detail ?? `Mia can't take calls right now (error ${res.status}).`);
}
