import { useEffect, useRef, useState, type ReactNode } from "react";

import type { ConversationItem } from "../lib/conversation";
import { copyText, toJson } from "../lib/copy";
import { formatMs, type DroppedEvent, type ToolEvent, type TurnMetrics } from "../lib/events";

/**
 * The call as one conversation: chat bubbles, and with "Show details" on, Mia's tool calls
 * (with their JSON), guardrail drops and each turn's latency in between. On desktop this is
 * the page's only scrolling area; on a phone the page scrolls as a whole.
 */
export function Conversation({
  items,
  live,
  details,
  onDetails,
  footer,
  onCopy,
}: {
  items: ConversationItem[];
  live: boolean;
  /** Kept by the page, so the choice survives the call ending. */
  details: boolean;
  onDetails: (on: boolean) => void;
  footer?: ReactNode;
  /** What "Copy JSON" puts on the clipboard (the call record, or a live snapshot). */
  onCopy?: () => Promise<unknown>;
}) {
  const box = useRef<HTMLDivElement>(null);
  const stuck = useRef(true); // following the newest line (until the caller scrolls up)
  const shown = details ? items : items.filter((i) => i.kind === "line");

  // Follow new lines by scrolling this box only (scrollIntoView would also move the page),
  // and only while the caller is at the bottom, so scrolling up to inspect isn't undone. On a
  // phone the box doesn't scroll (the page does), so nothing moves under the caller's thumb.
  useEffect(() => {
    const el = box.current;
    if (live && el && stuck.current && el.scrollHeight > el.clientHeight) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [live, shown.length]);

  // When a call ends, the live box is replaced by this one, which would start at the top: the
  // end of the call and the feedback form jumped out of view (Belinda, 2026-11-11). Start at
  // the bottom instead, where the caller was. Only this box moves, never the page.
  const ended = !live && footer != null;
  useEffect(() => {
    const el = box.current;
    if (ended && el && el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight;
  }, [ended]);

  return (
    <section
      aria-label="Conversation"
      className="flex flex-col rounded-2xl border border-line bg-surface lg:min-h-0 lg:flex-1"
    >
      <header className="flex items-center gap-3 border-b border-line px-4 py-3">
        <h2 className="font-semibold">Conversation</h2>
        {live && (
          <span className="flex items-center gap-1.5 text-xs text-ok">
            <span className="size-2 animate-pulse rounded-full bg-ok" /> live
          </span>
        )}
        <span className="ml-auto" />
        {onCopy && <CopyButton getData={onCopy} />}
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
          Show details
          <input
            type="checkbox"
            role="switch"
            checked={details}
            onChange={(e) => onDetails(e.target.checked)}
            className="peer sr-only"
          />
          <span
            aria-hidden
            className="relative h-5 w-9 rounded-full bg-line transition peer-checked:bg-brand peer-focus-visible:ring-2 peer-focus-visible:ring-accent after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-surface after:transition peer-checked:after:translate-x-4"
          />
        </label>
      </header>

      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          stuck.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="flex flex-col gap-3 p-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain"
      >
        {shown.length === 0 ? (
          <p className="text-sm text-muted">
            {live
              ? "Mia is joining…"
              : "Your conversation with Mia shows here. Turn on details to see every tool call she makes and how long each step takes."}
          </p>
        ) : (
          shown.map((item) =>
            item.kind === "line" ? (
              <Line key={item.id} item={item} details={details} />
            ) : item.kind === "tool" ? (
              <Tool key={item.id} e={item.event} />
            ) : (
              <Dropped key={item.id} e={item.event} />
            ),
          )
        )}
        {footer}
      </div>
    </section>
  );
}

/** Copies the call as JSON, for feedback notes; says "Copied" (or why not) for 2 s. */
function CopyButton({ getData }: { getData: () => Promise<unknown> }) {
  const [state, setState] = useState<"idle" | "busy" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state !== "copied" && state !== "failed") return;
    const timer = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(timer);
  }, [state]);
  const label = {
    idle: "Copy JSON",
    busy: "Copying…",
    copied: "Copied",
    failed: "Couldn't copy",
  }[state];
  return (
    <button
      type="button"
      title="Copy the whole call (transcript, tool calls and their JSON, latency) to the clipboard"
      disabled={state === "busy"}
      onClick={async () => {
        setState("busy");
        try {
          setState((await copyText(toJson(await getData()))) ? "copied" : "failed");
        } catch {
          setState("failed");
        }
      }}
      className={`rounded-full border border-line px-3 py-1 text-sm transition hover:bg-raised focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
        state === "copied" ? "text-ok" : state === "failed" ? "text-warn" : "text-muted"
      }`}
    >
      <span aria-live="polite">{label}</span>
    </button>
  );
}

function Line({ item, details }: { item: ConversationItem & { kind: "line" }; details: boolean }) {
  const you = item.who === "you";
  const chips = details ? latencyChips(item.who, item.metrics) : [];
  return (
    <div className={`flex max-w-[85%] flex-col gap-1 ${you ? "self-end items-end" : "self-start"}`}>
      <p
        className={`rounded-2xl px-4 py-2 ${
          you ? "rounded-br-sm bg-caller text-caller-ink" : "rounded-bl-sm bg-raised text-ink"
        } ${you && !item.final ? "opacity-60" : ""}`}
      >
        <span className="sr-only">{you ? "You: " : "Mia: "}</span>
        {item.text}
      </p>
      {details && (chips.length > 0 || item.note || item.interrupted) && (
        <p className="flex flex-wrap gap-1 text-xs text-muted">
          {item.note && <span className="italic">{item.note}</span>}
          {item.interrupted && <span className="text-warn">interrupted</span>}
          {chips.map(([label, ms]) => (
            <span key={label} className="rounded bg-raised px-1.5 font-mono">
              {label} {formatMs(ms)}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function latencyChips(who: "you" | "mia", m: TurnMetrics | undefined): [string, number][] {
  if (!m) return [];
  const pairs: [string, number | undefined][] =
    who === "you"
      ? [
          ["end of turn", m.end_of_turn],
          ["STT", m.stt],
        ]
      : [
          ["total", m.e2e],
          ["LLM", m.llm_ttft],
          ["voice", m.tts_ttfb],
        ];
  return pairs.filter((p): p is [string, number] => typeof p[1] === "number");
}

function Tool({ e }: { e: ToolEvent }) {
  return (
    <details className="group min-w-0 self-stretch rounded-lg border border-line bg-raised text-sm">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-1.5">
        <span className="text-muted group-open:rotate-90 transition">›</span>
        <span className="font-mono text-xs font-semibold">{e.name}()</span>
        <span
          className={`rounded px-1.5 text-xs ${e.ok ? "bg-ok-soft text-ok" : "bg-danger-soft text-danger"}`}
        >
          {e.ok ? "ok" : "error"}
        </span>
        <span className="font-mono text-xs text-muted">{formatMs(e.ms)}</span>
      </summary>
      <div className="grid min-w-0 gap-2 px-3 pb-3">
        <Json label="Arguments" value={e.args} />
        <Json label="Result (what the LLM got back)" value={e.result} />
      </div>
    </details>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted">{label}</p>
      <pre className="rounded bg-code p-2 text-xs whitespace-pre-wrap text-code-ink [overflow-wrap:anywhere]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function Dropped({ e }: { e: DroppedEvent }) {
  return (
    <p className="self-stretch rounded-lg bg-warn-soft px-3 py-1.5 text-xs text-warn">
      <span className="font-semibold">Guardrail dropped</span>{" "}
      <span className="font-mono">
        {e.tool}({e.args})
      </span>
      : {e.why}
    </p>
  );
}
