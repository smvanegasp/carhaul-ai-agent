import { useEffect, useState } from "react";

import { Conversation } from "../call/Conversation";
import { ErrorBoundary } from "../call/ErrorBoundary";
import { Insights } from "../call/Insights";
import {
  CallError,
  fetchCall,
  fetchCalls,
  type CallRecord,
  type CallSummary,
} from "../lib/api";
import { buildConversation } from "../lib/conversation";
import type { MiaEvent, TurnEvent } from "../lib/events";
import {
  formatDuration,
  formatUsd,
  formatWhen,
  outcomeLabel,
} from "../lib/format";

type Load<T> =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; data: T };

function message(err: unknown): string {
  return err instanceof CallError
    ? err.message
    : "Something went wrong loading calls.";
}

/**
 * Past calls: the latest calls (GET /api/calls) and, for the one picked, the same conversation
 * view and stats as a live call, rebuilt from the record the worker saved. On desktop the list
 * and the call sit side by side and each scrolls on its own; on a phone it's the list, then
 * the call with a way back.
 */
export function PastCalls({
  room,
  onOpen,
  active,
}: {
  room: string | null;
  onOpen: (room: string | null) => void;
  /** Reload the list whenever the view is shown (a call may have just ended). */
  active: boolean;
}) {
  const [list, setList] = useState<Load<CallSummary[]>>({ kind: "loading" });
  const [showTests, setShowTests] = useState(false);
  const shown: Load<CallSummary[]> =
    list.kind === "ok" && !showTests
      ? {
          kind: "ok",
          data: list.data.filter((c) => !c.room.startsWith("smoke-")),
        }
      : list;

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    fetchCalls()
      .then((data) => !cancelled && setList({ kind: "ok", data }))
      .catch(
        (err) =>
          !cancelled && setList({ kind: "error", message: message(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [active]);

  return (
    <div className="flex flex-col gap-4 lg:grid lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(260px,320px)_1fr]">
      <section
        aria-label="Past calls"
        className={`flex flex-col rounded-2xl border border-line bg-surface lg:min-h-0 ${room ? "hidden lg:flex" : ""}`}
      >
        <header className="border-b border-line px-4 py-3">
          <h2 className="font-semibold">Past calls</h2>
          <div className="flex items-center justify-between gap-2 text-xs text-muted">
            <span>The latest 50, newest first.</span>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={showTests}
                onChange={(e) => setShowTests(e.target.checked)}
                className="size-3.5 accent-[var(--brand)]"
              />
              Test calls
            </label>
          </div>
        </header>
        <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
          <CallList list={shown} selected={room} onOpen={onOpen} />
        </div>
      </section>

      <div
        className={`flex flex-col lg:min-h-0 ${room ? "" : "hidden lg:flex"}`}
      >
        {room ? (
          <ErrorBoundary
            key={room}
            fallback={<Note>This call hit a display error.</Note>}
          >
            <CallDetail room={room} onBack={() => onOpen(null)} />
          </ErrorBoundary>
        ) : (
          <Note>
            Pick a call to see its conversation, tool calls and latency.
          </Note>
        )}
      </div>
    </div>
  );
}

function CallList({
  list,
  selected,
  onOpen,
}: {
  list: Load<CallSummary[]>;
  selected: string | null;
  onOpen: (room: string) => void;
}) {
  if (list.kind === "loading")
    return <p className="p-4 text-sm text-muted">Loading calls…</p>;
  if (list.kind === "error") {
    return (
      <p role="alert" className="p-4 text-sm text-danger">
        {list.message}
      </p>
    );
  }
  if (list.data.length === 0) {
    return (
      <p className="p-4 text-sm text-muted">
        No calls yet. Call Mia and it shows up here.
      </p>
    );
  }
  return (
    <ul className="flex flex-col p-2">
      {list.data.map((c) => {
        const on = c.room === selected;
        return (
          <li key={c.room}>
            <button
              type="button"
              onClick={() => onOpen(c.room)}
              aria-current={on ? "true" : undefined}
              className={`flex w-full flex-col gap-0.5 rounded-xl px-3 py-2.5 text-left transition focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none ${
                on ? "bg-raised" : "hover:bg-raised/60"
              }`}
            >
              <span className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-medium text-ink">
                  {formatWhen(c.started_at)}
                </span>
                <span className="font-mono text-xs text-muted tabular-nums">
                  {formatDuration(c.duration_s)}
                </span>
              </span>
              <span className="flex items-baseline justify-between gap-2 text-xs text-muted">
                <span>{outcomeLabel(c)}</span>
                {c.quote_total != null && (
                  <span className="font-medium text-ink">
                    {formatUsd(c.quote_total)}
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Older records may have no events (too big to keep); rebuild the turns from the transcript. */
function eventsOf(record: CallRecord): MiaEvent[] {
  if (record.events?.length) return record.events;
  const start = Date.parse(record.started_at);
  return (record.transcript ?? []).map((line, i): TurnEvent => ({
    type: "turn",
    seq: i,
    t: line.t,
    at: start + line.t * 1000,
    role: line.role,
    kind: line.kind as TurnEvent["kind"],
    text: line.text,
    metrics: {},
    speaking_s: null,
    interrupted: false,
  }));
}

function CallDetail({ room, onBack }: { room: string; onBack: () => void }) {
  const [record, setRecord] = useState<Load<CallRecord>>({ kind: "loading" });
  const [details, setDetails] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    // Right after a call the worker may still be saving it ("See this call" links here):
    // try a few more times before saying it isn't saved.
    const attempt = (left: number) =>
      fetchCall(room)
        .then((data) => !cancelled && setRecord({ kind: "ok", data }))
        .catch((err) => {
          if (cancelled) return;
          if (left > 0) timer = setTimeout(() => attempt(left - 1), 2500);
          else setRecord({ kind: "error", message: message(err) });
        });
    void attempt(4);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [room]);

  const back = (
    <button
      type="button"
      onClick={onBack}
      className="self-start text-sm text-brand underline-offset-2 hover:underline lg:hidden"
    >
      ← All calls
    </button>
  );
  if (record.kind !== "ok") {
    return (
      <div className="flex flex-col gap-3">
        {back}
        {record.kind === "loading" ? (
          <Note>Loading the call…</Note>
        ) : (
          <Note>
            <span role="alert" className="text-danger">
              {record.message}
            </span>
          </Note>
        )}
      </div>
    );
  }

  const call = record.data;
  const events = eventsOf(call);
  const rating = call.feedback?.[0];
  return (
    <div className="flex flex-col gap-4 lg:min-h-0 lg:flex-1">
      {back}
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 rounded-2xl border border-line bg-surface px-4 py-3 text-sm">
        <span className="font-semibold text-ink">
          {formatWhen(call.started_at)}
        </span>
        <span className="text-muted">
          {formatDuration(call.duration_s)} long
        </span>
        <span className="text-muted">{outcomeLabel(call)}</span>
        {rating && (
          <span className="text-muted">
            Caller rated it{" "}
            <span className="font-medium text-ink">{rating.rating}/5</span>
            {rating.comment ? `: “${rating.comment}”` : ""}
          </span>
        )}
      </header>
      <div className="flex flex-col gap-4 xl:grid xl:min-h-0 xl:flex-1 xl:grid-cols-[1fr_320px]">
        <div className="flex flex-col lg:min-h-0 lg:flex-1 xl:flex-none">
          <Conversation
            items={buildConversation([], events)}
            live={false}
            details={details}
            onDetails={setDetails}
          />
        </div>
        <div className="xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain">
          <Insights events={events} />
        </div>
      </div>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-2xl border border-line bg-surface p-4 text-sm text-muted">
      {children}
    </p>
  );
}
