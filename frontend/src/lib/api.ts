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
