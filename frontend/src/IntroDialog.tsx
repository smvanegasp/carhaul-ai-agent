import { useCallback, useEffect, useRef, useState } from "react";

const SEEN_KEY = "mia.intro.seen";
export const AUTO_CLOSE_MS = 15_000;

function seenThisSession(): boolean {
  try {
    return sessionStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * What this is, and the disclosure, as a popup (Sergio, 2026-11-10: people should read it, and
 * the page feels more organized without it in the header). It opens on the first visit of a
 * browser session and closes by itself after 15 s; hovering it or using the keyboard in it
 * pauses the timer (focus alone doesn't: the "Got it" button gets focus as it opens).
 * The header's "About" button opens it again (then it stays until closed).
 */
export function useIntro() {
  const [open, setOpen] = useState(() => !seenThisSession());
  const [auto, setAuto] = useState(open);
  const close = useCallback(() => {
    setOpen(false);
    try {
      sessionStorage.setItem(SEEN_KEY, "1");
    } catch {
      // shown again next visit; fine
    }
  }, []);
  const show = () => {
    setAuto(false);
    setOpen(true);
  };
  return { open, auto, close, show };
}

export function IntroDialog({
  open,
  auto,
  onClose,
}: {
  open: boolean;
  auto: boolean;
  onClose: () => void;
}) {
  const [left, setLeft] = useState(AUTO_CLOSE_MS);
  const [paused, setPaused] = useState(false);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) {
      setLeft(AUTO_CLOSE_MS);
      button.current?.focus({ preventScroll: true });
    }
  }, [open]);

  useEffect(() => {
    if (!open || !auto || paused) return;
    const step = 100;
    const id = setInterval(() => setLeft((l) => l - step), step);
    return () => clearInterval(id);
  }, [open, auto, paused]);

  useEffect(() => {
    if (open && auto && left <= 0) onClose();
  }, [open, auto, left, onClose]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[color-mix(in_srgb,var(--ink)_35%,transparent)] p-4 backdrop-blur-[2px] sm:items-center"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="intro-title"
        onClick={(e) => e.stopPropagation()}
        onPointerEnter={() => setPaused(true)}
        onPointerLeave={() => setPaused(false)}
        onKeyDown={(e) => e.key !== "Escape" && setPaused(true)}
        className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-line bg-surface shadow-xl"
      >
        <div className="flex flex-col gap-4 p-6">
          <div>
            <p className="text-xs font-medium tracking-wide text-brand uppercase">
              F&amp;F car shipping
            </p>
            <h2 id="intro-title" className="font-display text-2xl text-ink">
              Meet Mia
            </h2>
          </div>
          <p className="text-sm leading-relaxed text-ink">
            Mia is an AI voice assistant that gives{" "}
            <strong>open car-shipping quotes</strong>. Tell her where your car
            is going from and to, and its year, make and model, and she'll give
            you a price in about a minute.
          </p>
          <ul className="flex flex-col gap-2 text-sm text-muted">
            <li>
              <span className="font-medium text-ink">Call from this page.</span>{" "}
              Allow the microphone and talk naturally; calls last up to 6
              minutes.
            </li>
            <li>
              <span className="font-medium text-ink">See how she works.</span>{" "}
              "Show details" reveals every tool call and how long each step
              took; Past calls and Stats show every call.
            </li>
          </ul>
          <div className="rounded-xl bg-raised p-3 text-sm text-ink">
            <span className="font-semibold">Disclosure:</span> this is a demo
            built by Sergio. If you ask to speak with a licensed representative,
            Mia transfers your call to Sergio's personal phone. Calls are saved
            as transcripts to improve Mia.
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted" aria-live="off">
              {auto
                ? paused
                  ? "Paused"
                  : `Closes in ${Math.ceil(left / 1000)} s`
                : ""}
            </span>
            <button
              ref={button}
              type="button"
              onClick={onClose}
              className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-brand-ink transition hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
            >
              Got it
            </button>
          </div>
        </div>
        {auto && (
          <div className="h-1 bg-raised" aria-hidden>
            <div
              className="h-full bg-accent transition-[width] duration-100 ease-linear"
              style={{ width: `${(left / AUTO_CLOSE_MS) * 100}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
