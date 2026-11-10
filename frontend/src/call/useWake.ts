import { useCallback, useEffect, useState } from "react";

import { CallError, wakeMia } from "../lib/api";
import type { WakeStep } from "../lib/wake";

/** Mia's voice worker, as the call page sees it (backend/app/worker.py). */
export type Wake =
  | { kind: "checking" }
  | { kind: "starting"; since: number; step: WakeStep }
  | { kind: "ready" }
  | { kind: "unavailable"; message: string };

const POLL_MS = 4000;
const GIVE_UP_MS = 4 * 60_000; // a cold start takes about a minute

function message(err: unknown): string {
  return err instanceof CallError ? err.message : "Mia can't take calls right now.";
}

/**
 * On AWS Mia's worker only runs around calls: opening the page wakes it, and this polls until
 * it's ready. Locally (docker compose) the API always answers "ready".
 */
export function useWake() {
  const [wake, setWake] = useState<Wake>({ kind: "checking" });
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    if (!polling) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const since = Date.now();
    const done = (next: Wake) => {
      setWake(next);
      setPolling(false);
    };
    const tick = async () => {
      try {
        const status = await wakeMia();
        if (cancelled) return;
        if (status.state === "ready") return done({ kind: "ready" });
        if (status.state === "unavailable") {
          return done({ kind: "unavailable", message: status.detail || message(null) });
        }
        if (Date.now() - since > GIVE_UP_MS) {
          return done({
            kind: "unavailable",
            message: "Mia is taking too long to wake up. Try again in a few minutes.",
          });
        }
        setWake({ kind: "starting", since, step: status.step ?? null });
        timer = setTimeout(tick, POLL_MS);
      } catch (err) {
        if (!cancelled) done({ kind: "unavailable", message: message(err) });
      }
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [polling]);

  /** Wake her again (e.g. she went back to sleep while the page sat open). */
  const recheck = useCallback(() => {
    setWake({ kind: "checking" });
    setPolling(true);
  }, []);

  return { wake, recheck };
}
